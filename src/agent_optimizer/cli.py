from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import typer
from typer._click import ClickException
from typer._click.core import Abort, Exit

from agent_optimizer.config import load_agent, load_experiment
from agent_optimizer.catalog import DATASETS as CATALOG_DATASETS
from agent_optimizer.contracts import ConfigurationError, UnavailableError, jsonable
from agent_optimizer.runner import preflight, run_experiment
from agent_optimizer.registry import Registry
from agent_optimizer.network import network_environment
from agent_optimizer.setup_wizard import (component_inventory, prepare_selection,
                                          _bounded_tasks, choose_editable_file, requires_command,
                                          supports_generated_profile, wizard_arguments,
                                          write_experiment)
from agent_optimizer.terminal_report import PreparationStatus, ProgressDisplay
from agent_optimizer.terminal_report import SessionProgress
from agent_optimizer.session import SessionInterrupted, run_session
from agent_optimizer.terminal_style import style
from agent_optimizer.locale import MESSAGES, current_language, human, render_diagnostic, report_language, t
from agent_optimizer.results import write_json
from agent_optimizer.readiness import collect_dataset, collect_plan


def show(value):
    print(json.dumps(jsonable(value), indent=2, ensure_ascii=False, allow_nan=False))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        language = current_language()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if argv and argv[0] == "rerank":
        print(style("error:", "error", stream=sys.stderr) + " " + human(
            "rerank is deferred; configure the objective for a new run. Stored reports and frozen selections remain available; see deferred/README.md"), file=sys.stderr)
        return 2
    previous = sys.dont_write_bytecode
    if argv and argv[0] == "doctor":
        sys.dont_write_bytecode = True
    try:
        command = typer.main.get_command(app)
        if language == "en":
            localize_click_help(command)
        return command.main(args=argv, prog_name="agent-opt", standalone_mode=False) or 0
    except ClickException as exc:
        print(f"{style('error:', 'error', stream=sys.stderr)} {exc.format_message()}", file=sys.stderr)
        return exc.exit_code
    except Exit as exc:
        return exc.exit_code
    except Abort:
        return 130
    finally:
        sys.dont_write_bytecode = previous


app = typer.Typer(help="여러 Agent의 최적화 실험을 위한 작업 도구", no_args_is_help=True,
                  add_completion=False,
                  epilog=('저장소에서 시작: make setup-core. 기존 실험을 선택하려면 agent-opt tui의 '
                          '"기존 실험 실행", 새 설정은 agent-opt init(대화형)을 사용하세요. '
                          '데이터셋은 직접 선택하며 모델 없는 합성 예제는 README.md를 참고하세요.'))
dataset_app = typer.Typer(help="데이터셋 목록 표시 및 명시적으로 선택한 데이터셋 준비", no_args_is_help=True)
app.add_typer(dataset_app, name="datasets")


def localize_click_help(command):
    """Translate static help on this invocation's Click command tree."""
    for attribute in ("help", "short_help", "epilog"):
        value = getattr(command, attribute, None)
        if value in MESSAGES:
            setattr(command, attribute, t(value, lang="en"))
    for parameter in command.params:
        value = getattr(parameter, "help", None)
        if value in MESSAGES:
            parameter.help = t(value, lang="en")
    for child in getattr(command, "commands", {}).values():
        localize_click_help(child)


def _invoke(command: str, **options) -> int:
    return _dispatch(SimpleNamespace(command=command, **options))


def _launch_existing(spec: dict, registry: Registry, *, output: Path | None = None) -> int | None:
    registry.load_project(spec["_root"])
    registry.load_plugins(spec["_root"], {"harnesses": spec.get("plugins", {}).get("harnesses", {})})
    launchers = [getattr(registry.resolve("harnesses", profile["adapter"]), "launch_existing", None)
                 for profile in spec["_profiles"]]
    if any(launcher is not None for launcher in launchers):
        if output is not None:
            raise ConfigurationError("전용 실행 프로필은 --output을 지원하지 않습니다")
        if len(spec["_profiles"]) != 1 or len(spec["_agents"]) != 1:
            raise ConfigurationError("전용 실행 프로필은 단일 Agent·하네스 실험에서만 사용할 수 있습니다")
        previous = Path.cwd()
        try:
            os.chdir(spec["_root"])
            return launchers[0](spec)
        finally:
            os.chdir(previous)
    return None


def _tui_model_environment(spec: dict, env: dict[str, str] | None = None) -> dict[str, str]:
    from agent_optimizer.model_input import ensure_model_api, ensure_model_selector

    profiles = spec["_profiles"]
    research = any(stage["optimizer"] in {"gepa", "meta_harness", "ecdysis"}
                   for stage in spec.get("stages", []))
    model_keys = {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"}
    api = research or any(profile["adapter"] != "opencode" and
                          model_keys.issubset(profile.get("runtime", {}).get("env_passthrough", []))
                          for profile in profiles)
    staged = dict(os.environ if env is None else env)
    if api:
        staged = ensure_model_api(staged)
    for profile in profiles:
        if profile["adapter"] == "opencode":
            staged = ensure_model_selector(staged, profile.get("model_env", "AGENT_OPT_MODEL"))
    return staged


@app.command("plugins")
def plugins_command(project_root: Path | None = None) -> int:
    """구현된 연동 목록 표시."""
    return _invoke("plugins", project_root=project_root or Path.cwd())


@app.command("prepare")
def prepare_command(experiment: Path, offline: bool = False) -> int:
    """직접 선택한 실험의 버전 고정 연동 자산을 준비합니다."""
    return _invoke("prepare", experiment=experiment, offline=offline)


@app.command("doctor")
def doctor_command(dataset: str | None = None, plan: Path | None = None,
                   project_root: Path | None = None,
                   json_output: bool = typer.Option(False, "--json", help="기계가 읽을 수 있는 단일 진단 결과 출력"),
                   model: bool = typer.Option(False, "--model", help="--plan 필요; 모델 API를 명시적으로 호출")) -> int:
    """도구·선택 데이터셋·실험 계획의 준비 상태 진단. --dataset/--plan은 읽기 전용."""
    if dataset and plan:
        raise typer.BadParameter("--dataset과 --plan은 함께 사용할 수 없습니다")
    return _invoke("doctor", dataset=dataset, plan=plan, project_root=project_root or Path.cwd(),
                   json=json_output, model=model)


@dataset_app.command("list")
def datasets_list(project_root: Path | None = None) -> int:
    """등록 데이터셋 목록 표시."""
    return _invoke("datasets", dataset_action="list", project_root=project_root or Path.cwd())


@dataset_app.command("prepare")
def datasets_prepare(name: str | None = typer.Argument(None, help="등록된 데이터셋 ID 또는 로컬 tasks.json"),
                     project_root: Path | None = None,
                     evaluator: str | None = typer.Option(None, help="로컬 tasks.json에는 필수: file.py:Symbol"),
                     offline: bool = typer.Option(False, help="검증된 캐시 자산만 재사용")) -> int:
    """직접 선택한 데이터셋 준비."""
    return _invoke("datasets", dataset_action="prepare", name=name,
                   project_root=project_root or Path.cwd(), evaluator=evaluator, offline=offline)


@app.command("init")
def init_command(project_root: Path | None = None,
                 profile: str | None = typer.Option(None, "--profile", help="명시적으로 선택하는 준비된 실험 프로필"),
                 workspace: Path | None = typer.Option(None, "--workspace", help="선택형 실험 작업공간"),
                 agent: str | None = typer.Option(None, help="로컬 소스 경로 또는 Git URL(Git이면 --revision 지정)"),
                 revision: str | None = None, name: str | None = None,
                 command: str | None = typer.Option(None, "--command", help="명령 하네스의 Agent argv: 인용을 분리하지만 셸 확장·파이프·리다이렉션은 실행하지 않음"),
                 editable: list[str] | None = typer.Option(None, "--editable", help="수정 허용 Agent 경로/패턴(반복 가능)"),
                 prompt_file: str = "prompts/system.md",
                 dataset: list[str] | None = typer.Option(None, "--dataset", help="데이터셋 직접 선택: 등록 ID 또는 로컬 tasks.json(반복 가능)"),
                 evaluator: str | None = None, metric: str = "passed",
                 direction: Literal["maximize", "minimize"] = typer.Option("maximize", "--direction"),
                 harness: str = "command", optimizer: list[str] | None = typer.Option(None, "--optimizer", help="명시적으로 선택할 Optimizer ID(필수, 반복 가능; 예: baseline)"),
                 optimizer_config: str | None = None, scaffold_file: str | None = None,
                 target_file: str | None = None, max_tasks: int = 9, max_trials: int | None = None,
                 max_wall_time_seconds: float = 3600, trial_timeout_seconds: float = 120,
                 offline: bool = False,
                 yes: bool = typer.Option(False, help="TTY 없이 준비를 확인하고 진행")) -> int:
    """직접 선택한 데이터셋으로 실험 설정 생성."""
    if profile is not None or workspace is not None:
        return _invoke("init-profile", profile=profile, workspace=workspace, agent=agent,
                       dataset=dataset, evaluator=evaluator, optimizer=optimizer, editable=editable,
                       command_text=command, revision=revision, name=name)
    if (not any((agent, dataset, editable, command, name, revision, optimizer))
            and not yes and sys.stdin.isatty() and sys.stderr.isatty()):
        try:
            arguments = wizard_arguments((project_root or Path.cwd()).absolute(), execute=False)
        except EOFError:
            print(human("입력이 종료되어 설정을 만들지 않았습니다"), file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("\n" + human("설정 만들기가 중단되었습니다"), file=sys.stderr)
            return 130
        except ConfigurationError as exc:
            print(f"{style('error:', 'error', stream=sys.stderr)} {human(str(exc))}", file=sys.stderr)
            return 2
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        if code:
            return code
        print(output.getvalue(), end="")
        prepared = json.loads(output.getvalue())
        target = prepared.get("experiment") or prepared["session"]
        if "session" in prepared:
            checks = "\n".join(f"       agent-opt doctor --plan {item['experiment']}"
                               for item in prepared["experiments"])
            print(f"{human('설정 생성')}: {target}\n{human('다음')}: {human('각 데이터셋의 계획 진단')}\n{checks}\n"
                  f"       agent-opt run-session {target}", file=sys.stderr)
        else:
            print(f"{human('설정 생성')}: {target}\n{human('다음')}: agent-opt doctor --plan {target}\n"
                  f"       agent-opt run {target}", file=sys.stderr)
        return 0
    return _invoke("init", project_root=project_root or Path.cwd(), agent=agent,
                   revision=revision, name=name, command_text=command,
                   editable=editable, prompt_file=prompt_file, dataset=dataset,
                   evaluator=evaluator, metric=metric, direction=direction,
                   harness=harness, optimizer=optimizer, optimizer_config=optimizer_config,
                   scaffold_file=scaffold_file, target_file=target_file, max_tasks=max_tasks,
                   max_trials=max_trials, max_wall_time_seconds=max_wall_time_seconds,
                   trial_timeout_seconds=trial_timeout_seconds, offline=offline, yes=yes)


@app.command("tui")
def tui_command(project_root: Path | None = None) -> int:
    """기존 실험 선택 또는 새 실험 생성 후 실행(TTY 필요)."""
    return _invoke("tui", project_root=project_root or Path.cwd())


@app.command("run-session")
def run_session_command(session: Path, output: Path | None = None,
                        jobs: int = typer.Option(2, "--jobs", min=1)) -> int:
    """선택한 데이터셋마다 독립 평가기로 병렬 실행(기본 2개)."""
    return _invoke("run-session", session=session, output=output, jobs=jobs)


@app.command("agents")
def agents_command(root: Path = Path("examples")) -> int:
    """독립 등록된 Agent 대상 목록 표시."""
    return _invoke("agents", root=root)


@app.command("plan")
def plan_command(experiment: Path) -> int:
    """실행 없이 실험 조합 확인."""
    return _invoke("plan", experiment=experiment)


@app.command("run")
def run_command(experiment: Path, output: Path | None = None) -> int:
    """준비된 실험 실행 및 보고서 작성."""
    return _invoke("run", experiment=experiment, output=output)


@app.command("report")
def report_command(run_dir: Path, csv: Path | None = None,
                   html: bool = typer.Option(False, "--html", help="독립 HTML 보고서 재생성")) -> int:
    """실행 요약 확인 또는 HTML 재생성."""
    return _invoke("report", run_dir=run_dir, csv=csv, html=html)


def _dispatch(args):
    registry = Registry()
    try:
        if args.command != "doctor" or not (args.dataset or args.plan):
            os.environ.update(network_environment())
        if args.command == "plugins":
            registry.load_project(args.project_root.absolute())
            show(registry.describe())
        elif args.command == "prepare":
            from agent_optimizer.integrations import prepare_pointer
            show(prepare_pointer(args.experiment, offline=args.offline))
        elif args.command == "datasets":
            root = args.project_root.absolute()
            inventory, _, _ = component_inventory(root)
            if args.dataset_action == "list":
                rows = {name: {**factory().describe(), "name": name}
                        for name, factory in inventory.factories["datasets"].items()}
                for name, description in CATALOG_DATASETS.items():
                    if name in rows:
                        if any(rows[name].get(field) != description[field]
                               for field in ("task_form", "evaluator", "revision")):
                            raise ConfigurationError(f"등록된 데이터셋 설명이 카탈로그와 다릅니다: {name}")
                    else:
                        rows[name] = dict(description)
                show([rows[name] for name in sorted(rows)])
            else:
                if not args.name:
                    raise ConfigurationError("Choose a dataset name or a local tasks.json")
                result, _, _ = prepare_selection(root, args.name, evaluator=args.evaluator,
                                                  offline=args.offline)
                show(result)
        elif args.command == "init-profile":
            if not args.profile or args.workspace is None:
                raise ConfigurationError("--profile과 --workspace를 함께 지정하세요")
            if any((args.agent, args.dataset, args.evaluator, args.optimizer, args.editable,
                    args.command_text, args.revision, args.name)):
                raise ConfigurationError("--profile에는 Agent·데이터셋·실행 명령 옵션을 섞지 마세요")
            from agent_optimizer.integrations import write_pending_experiment
            target = write_pending_experiment(args.workspace, args.profile)
            show({"experiment": target, "profile": args.profile, "ready": False})
        elif args.command == "init":
            if not args.dataset:
                raise ConfigurationError("Select a dataset explicitly with --dataset")
            if not args.agent or not args.editable:
                raise ConfigurationError("--agent와 --editable을 지정하세요")
            command = None
            if args.command_text is not None:
                try:
                    command = shlex.split(args.command_text)
                except ValueError as exc:
                    raise ConfigurationError(f"잘못된 Agent 실행 명령: {exc}") from exc
            if command is not None and (not isinstance(command, list) or not command or not all(
                    isinstance(part, str) and part for part in command)):
                raise ConfigurationError("Agent argv must be a nonempty string array")
            if not args.yes:
                raise ConfigurationError("Inspect the choices then pass --yes to confirm preparation")
            if not args.optimizer:
                raise ConfigurationError("Optimizer를 --optimizer ID로 명시하세요 (예: --optimizer baseline)")
            root = args.project_root.absolute()
            agent = args.agent if args.revision else Path(args.agent)
            if isinstance(agent, Path) and not agent.is_absolute():
                agent = (root / agent).resolve()
            if args.revision and not args.revision.strip():
                raise ConfigurationError("A pinned Git Agent requires a revision")
            name = args.name or (agent.name if isinstance(agent, Path) and agent.is_dir() else "agent")
            name = name.lower().replace(" ", "-")
            inventory, _, _ = component_inventory(root)
            adapter = inventory.resolve("harnesses", args.harness)
            uses_command = requires_command(adapter)
            if uses_command and command is None:
                raise ConfigurationError("이 하네스에는 --command가 필요합니다")
            if not uses_command and command is not None:
                raise ConfigurationError("선택한 하네스는 Agent 실행 명령을 받지 않습니다")
            if not supports_generated_profile(adapter):
                raise ConfigurationError("전용 하네스 프로필이 필요합니다. 기존 experiment.toml을 사용하세요")
            chosen = args.optimizer
            custom_configs = json.loads(args.optimizer_config) if args.optimizer_config else {}
            if (not isinstance(custom_configs, dict)
                    or not all(isinstance(name, str) and isinstance(options, dict)
                               for name, options in custom_configs.items())):
                raise ConfigurationError("--optimizer-config must be a JSON mapping of optimizer names to options")
            for optimizer in chosen:
                inventory.resolve("optimizers", optimizer)
            target = (choose_editable_file(agent, args.editable, explicit=args.target_file)
                      if "gepa" in chosen else None)
            scaffold = (choose_editable_file(agent, args.editable, suffix=".py",
                                             explicit=args.scaffold_file)
                        if any(o in {"meta_harness", "ecdysis"} for o in chosen) else None)
            harness = {"adapter": args.harness}
            if command is not None:
                harness["command"] = command
            if args.revision:
                harness["revision"] = args.revision
            experiments = []
            multiple = len(args.dataset) > 1
            with contextlib.ExitStack() as rollback:
                for index, dataset_name in enumerate(args.dataset):
                    data, plugins, dependencies = prepare_selection(
                        root, dataset_name, evaluator=args.evaluator, offline=args.offline)
                    document = _bounded_tasks(json.loads(Path(data["benchmark"]).read_text(encoding="utf-8")),
                                              args.max_tasks)
                    train = sum(t["split"] == "train" for t in document["tasks"])
                    validation = sum(t["split"] == "validation" for t in document["tasks"])
                    if train == 0 and any(o in {"gepa", "meta_harness", "ecdysis"} for o in chosen):
                        raise ConfigurationError("Research optimizers require at least one train task")
                    stages = []
                    for stage_index, optimizer in enumerate(chosen):
                        if optimizer == "gepa":
                            config = {"file": target, "iterations": 3, "batch_size": 4,
                                      "metric": args.metric, "direction": args.direction}
                        elif optimizer in {"meta_harness", "ecdysis"}:
                            config = {"file": scaffold, **({"rounds": 3} if optimizer == "ecdysis"
                                                          else {"iterations": 3}),
                                      "direction": args.direction}
                            if optimizer == "ecdysis":
                                config.update(score_metric="solve_rate" if args.metric == "passed" else args.metric,
                                              failure_metric=args.metric)
                            else:
                                config["metric"] = args.metric
                        else:
                            config = custom_configs.get(optimizer, {})
                        config.update(custom_configs.get(optimizer, {}))
                        if optimizer == "gepa":
                            iterations, batch_size = config.get("iterations"), config.get("batch_size")
                            if (type(iterations) is not int or iterations < 1
                                    or type(batch_size) is not int or batch_size < 1):
                                raise ConfigurationError("GEPA iterations and batch_size must be positive integers")
                            batch = min(train, batch_size) + validation
                            limit = train + iterations * batch + (batch if config.get("merge") else 0)
                        elif optimizer == "meta_harness":
                            iterations = config.get("iterations")
                            if type(iterations) is not int or iterations < 1:
                                raise ConfigurationError("Meta-Harness iterations must be positive")
                            limit = train + iterations * (train + validation)
                        elif optimizer == "ecdysis":
                            rounds = config.get("rounds")
                            if type(rounds) is not int or rounds < 1:
                                raise ConfigurationError("Ecdysis rounds must be positive")
                            limit = (rounds + 1) * train + validation
                        else:
                            limit = train * 3 + validation * 3
                        stages.append({"id": f"opt-{stage_index}-{optimizer.replace('_', '-')}",
                                       "optimizer": optimizer, "config": config,
                                       "max_trials": max(1, limit)})
                    label = re.sub(r"[^a-zA-Z0-9_.-]", "-", Path(dataset_name).stem)
                    experiment_name = f"{name}-{index + 1}-{label}" if multiple else name
                    folder = (root / "runs" / "configs" / name / f"{index + 1}-{label}" if multiple
                              else root / "runs" / "configs" / name)
                    experiment = write_experiment(folder, agent=agent, harness=harness, dataset=data,
                                                  stages=stages, plugins=plugins, dependencies=dependencies,
                                                  name=experiment_name, editable=args.editable,
                                                  prompt_file=args.prompt_file, max_tasks=args.max_tasks,
                                                  project_root=root,
                                                  max_trials=args.max_trials,
                                                  wall_time=args.max_wall_time_seconds,
                                                  trial_timeout=args.trial_timeout_seconds,
                                                  objective_source=args.metric,
                                                  objective_direction=args.direction)
                    rollback.callback(shutil.rmtree, folder)
                    experiments.append({"dataset": dataset_name, "experiment": str(experiment)})
                if multiple:
                    target = root / "runs" / "configs" / name / "session.json"
                    if target.exists() or target.is_symlink():
                        raise ConfigurationError(f"Generated session already exists: {target}")
                    rollback.callback(target.unlink, missing_ok=True)
                    write_json(target, {"schema_version": 1, "name": name, "experiments": experiments})
                    show({"session": target, "experiments": experiments})
                else:
                    show({"experiment": experiments[0]["experiment"], "dataset": args.dataset[0],
                          "stages": [s["id"] for s in stages]})
                rollback.pop_all()
        elif args.command == "tui":
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise ConfigurationError(t("TUI requires a TTY for both input and output"))
            try:
                print("\n" + human("실험 시작: 1. 기존 실험 실행  2. 새 실험 만들고 실행  3. ACE-RTL + CVDP 예제"), file=sys.stderr)
                print(human("선택 [1/2/3]: "), end="", file=sys.stderr, flush=True)
                choice = input().strip()
                if choice in {"1", "3"}:
                    if choice == "3":
                        print(human("ACE-RTL 작업공간 경로: "), end="", file=sys.stderr, flush=True)
                        selected = input().strip()
                        if not selected:
                            raise ConfigurationError(human("ACE-RTL 작업공간 경로를 입력하세요"))
                        workspace = Path(selected).expanduser()
                        if not workspace.is_absolute():
                            workspace = args.project_root.absolute() / workspace
                        print(f"{human('선택한 작업공간')}: {workspace}\n"
                              + human("준비 작업: 고정 Git 소스·CVDP 데이터·driver·Docker 이미지"),
                              file=sys.stderr)
                        print(human("ACE-RTL 연동을 준비할까요? [y/N]: "), end="", file=sys.stderr, flush=True)
                        if input().strip().lower() not in {"y", "yes"}:
                            print(human("실험 준비를 취소했습니다"), file=sys.stderr)
                            return 2
                        output = io.StringIO()
                        with contextlib.redirect_stdout(output):
                            code = main(["init", "--profile", "ace-rtl", "--workspace", str(workspace)])
                        if code:
                            return code
                        experiment = Path(json.loads(output.getvalue())["experiment"])
                        with contextlib.redirect_stdout(sys.stderr):
                            code = main(["prepare", str(experiment)])
                        if code:
                            return code
                    else:
                        print(human("기존 experiment.toml 경로: "), end="", file=sys.stderr, flush=True)
                        selected = input().strip()
                        if not selected:
                            raise ConfigurationError(human("실험 설정 경로를 입력하세요"))
                        experiment = Path(selected).expanduser()
                        if not experiment.is_absolute():
                            experiment = args.project_root / experiment
                        experiment = experiment.resolve()
                    init_args = None
                elif choice == "2":
                    init_args = wizard_arguments(args.project_root.absolute())
                else:
                    raise ConfigurationError(human("1, 2 또는 3을 선택하세요"))
            except EOFError:
                print(style(human("TUI cancelled:"), "warning", stream=sys.stderr) + " " + human("input ended"), file=sys.stderr)
                return 2
            except KeyboardInterrupt:
                print("\n" + style(human("TUI interrupted"), "warning", stream=sys.stderr), file=sys.stderr)
                return 130
            if init_args is not None:
                print("\n  " + style(human("Preparing the selected dataset…"), "warning", stream=sys.stderr),
                      file=sys.stderr, flush=True)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(init_args)
                if code:
                    return code
                prepared = json.loads(output.getvalue())
                if "session" in prepared:
                    from agent_optimizer.model_input import session_environment
                    try:
                        staged = dict(os.environ)
                        for item in prepared["experiments"]:
                            staged = _tui_model_environment(load_experiment(Path(item["experiment"])), staged)
                        with session_environment(staged):
                            return main(["run-session", prepared["session"]])
                    except KeyboardInterrupt:
                        print("\n" + style(human("TUI interrupted"), "warning", stream=sys.stderr), file=sys.stderr)
                        return 130
                experiment = Path(prepared["experiment"])
            spec = load_experiment(experiment)
            from agent_optimizer.model_input import session_environment
            try:
                environment = _tui_model_environment(spec)
                with session_environment(environment):
                    if choice in {"1", "3"}:
                        report = collect_plan(experiment, registry)
                        print(f"{human('실험 설정')}: {experiment}", file=sys.stderr)
                        print(f"{human('계획 진단')}: {human('준비됨' if report['ready'] else '준비 부족')}", file=sys.stderr)
                        if not report["ready"]:
                            for check in report["checks"]:
                                if check["status"] != "ok":
                                    message, remedy = render_diagnostic(check)
                                    print(f"  {check['id']}: {message} {remedy}", file=sys.stderr)
                            return 2
                        if choice == "3":
                            print(f"{human('실도구 진단')}: {human('준비됨')}", file=sys.stderr)
                        print(human("이 실험을 실행할까요? [y/N]: "), end="", file=sys.stderr, flush=True)
                        if input().strip().lower() not in {"y", "yes"}:
                            print(human("실험 실행을 취소했습니다"), file=sys.stderr)
                            return 2
                    launched = _launch_existing(spec, registry)
                    if launched is not None:
                        return launched
                    with ProgressDisplay() as progress:
                        progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                        root, summary = run_experiment(spec, Registry(), on_event=progress)
                    show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"],
                          "report_html": root / "report.html"})
                    return 0 if summary["status"] == "completed" else 3
            except EOFError:
                print(style(human("TUI cancelled:"), "warning", stream=sys.stderr) + " " + human("input ended"), file=sys.stderr)
                return 2
            except KeyboardInterrupt:
                print("\n" + style(human("TUI interrupted"), "warning", stream=sys.stderr), file=sys.stderr)
                return 130
        elif args.command == "run-session":
            data = json.loads(args.session.read_text(encoding="utf-8"))
            if (data.get("schema_version") != 1 or not isinstance(data.get("experiments"), list)
                    or len(data["experiments"]) < 2):
                raise ConfigurationError("run-session requires at least two prepared experiments")
            base = args.output or args.session.parent.parents[1] / "sessions"
            import time
            import uuid
            session_started = time.monotonic()
            session_root = base / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                                   + "-" + uuid.uuid4().hex[:8])
            session_root.mkdir(parents=True, exist_ok=False)
            interrupted = False
            with SessionProgress([item["dataset"] for item in data["experiments"]]) as progress:
                try:
                    entries = run_session(data["experiments"], session_root, jobs=args.jobs,
                                          progress=progress)
                except SessionInterrupted as exc:
                    entries = exc.entries
                    interrupted = True
            from agent_optimizer.html_report import write_session_index
            index = write_session_index(session_root, entries, language=current_language())
            status = ("interrupted" if interrupted else "completed" if all(
                e["status"] == "completed" for e in entries) else "partial")
            write_json(session_root / "summary.json", {"status": status, "experiments": entries,
                                                       "session_wall_time_seconds": time.monotonic() - session_started,
                                                       "report_language": current_language()})
            show({"session_dir": session_root, "status": status, "index_html": index,
                   "reports": [session_root / e["report"] for e in entries if e["report"]]})
            return 130 if interrupted else 0 if status == "completed" else 3
        elif args.command == "doctor":
            if args.model and not args.plan:
                raise ConfigurationError("--model requires --plan")
            if args.dataset or args.plan:
                if args.dataset or args.model:
                    label = "dataset" if args.dataset else "plan-model"
                    with PreparationStatus(label, action="doctor", subject="check"):
                        report = (collect_dataset(args.project_root, args.dataset, registry) if args.dataset else
                                  collect_plan(args.plan, registry, model=True))
                else:
                    report = collect_plan(args.plan, registry)
                if args.json:
                    show(report)
                else:
                    status = "ready" if report["ready"] else "not ready"
                    print(f"{report['scope']} {human('readiness')}: "
                          + style(status, "success" if report["ready"] else "error"))
                    for row in report["checks"]:
                        message, remedy = render_diagnostic(row)
                        tone = {"ok": "success", "error": "error", "blocked": "warning"}.get(
                            row["status"], "warning")
                        print(f"[{style(row['status'], tone)}] {row['id']}: {message}")
                        if remedy:
                            print(f"  {style(t('remedy') + ':', 'warning')} {remedy}")
                return 0 if report["ready"] else 2
            raise ConfigurationError("agent-opt doctor --plan PATH 또는 --dataset ID를 지정하세요")
        elif args.command == "agents":
            show([load_agent(p) for p in sorted(args.root.rglob("agent.toml"))])
        elif args.command in {"plan", "run"}:
            spec = load_experiment(args.experiment.resolve())
            if args.command == "run":
                launched = _launch_existing(spec, registry, output=args.output)
                if launched is not None:
                    return launched
                with ProgressDisplay() as progress:
                    progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                    root, summary = run_experiment(spec, registry, args.output, on_event=progress)
                show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"]})
                return 0 if summary["status"] == "completed" else 3
            available, detail = True, ""
            try:
                preflight(spec, registry)
            except UnavailableError as exc:
                available, detail = False, str(exc)
            show({"valid": True, "integrations_ready": available, "detail": detail,
                  "matrix": [{"agent": a.id, "harness": h["id"]} for a in spec["_agents"] for h in spec["_profiles"]],
                  "sources": {a.id: a.source for a in spec["_agents"]},
                  "stages": spec.get("stages", []), "objective": spec["objective"],
                  "tasks_by_split": {s: sum(t.split == s for t in spec["_tasks"]) for s in ["train", "validation", "test"]},
                  "note": "Schema/registry validation only. Run doctor and environment checks before real execution."})
        elif args.command == "report":
            data = json.loads((args.run_dir / "summary.json").read_text())
            if args.html:
                from agent_optimizer.results import write_report_artifacts
                with PreparationStatus("html", action="report", subject="check"):
                    language = report_language(data, args.run_dir,
                                               override=os.environ.get("AGENT_OPT_LANG") or None)
                    target = write_report_artifacts(args.run_dir, data, language=language)
                show({"html": target, "status": data["status"]})
                return 0
            if args.csv:
                with PreparationStatus("csv", action="report", subject="check"):
                    records = [json.loads(s) for s in (args.run_dir / "events.jsonl").read_text().splitlines()]
                    records = [r for r in records if r.get("event") == "trial_completed"]
                    keys = sorted({k for r in records for k in r["metrics"]})
                    fixed = ["agent_id", "harness_id", "candidate_id", "task_id", "split", "repeat", "status"]
                    args.csv.parent.mkdir(parents=True, exist_ok=True)
                    with args.csv.open("w", newline="", encoding="utf-8") as stream:
                        writer = csv.DictWriter(stream, fieldnames=fixed + keys)
                        writer.writeheader()
                        for r in records:
                            writer.writerow({**{k: r[k] for k in fixed}, **r["metrics"]})
            show(data)
    except (ConfigurationError, UnavailableError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"{style('error:', 'error', stream=sys.stderr)} {human(str(exc))}", file=sys.stderr)
        return 2
    return 0
