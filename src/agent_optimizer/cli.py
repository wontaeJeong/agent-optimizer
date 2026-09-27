from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import re
import shlex
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import typer
from typer._click import ClickException
from typer._click.core import Abort, Exit

from agent_optimizer.config import load_agent, load_experiment, selected_pairs
from agent_optimizer.catalog import DATASETS as CATALOG_DATASETS, describe_choice, list_choices
from agent_optimizer.contracts import ConfigurationError, SourceSpec, UnavailableError, jsonable
from agent_optimizer.runner import preflight, run_experiment
from agent_optimizer.sources import validate_source
from agent_optimizer.registry import Registry
from agent_optimizer.network import network_environment
from agent_optimizer.setup_wizard import (component_inventory, prepare_selection,
                                           _bounded_tasks, choose_editable_file, requires_command,
                                           supports_generated_profile, wizard_arguments, write_experiment)
from agent_optimizer.terminal_report import PreparationStatus, ProgressDisplay
from agent_optimizer.terminal_report import SessionProgress
from agent_optimizer.session import SessionInterrupted, run_session
from agent_optimizer.terminal_style import style
from agent_optimizer.locale import MESSAGES, current_language, human, render_diagnostic, report_language, t
from agent_optimizer.results import write_json
from agent_optimizer.readiness import collect_dataset, collect_plan


def show(value):
    print(json.dumps(jsonable(value), indent=2, ensure_ascii=False, allow_nan=False))


def next_command(command: str) -> None:
    print(f"{human('다음')}: {command}", file=sys.stderr)


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
    if argv and argv[0] in {"doctor", "catalog"}:
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
                           '네 구성요소는 agent-opt catalog에서 조회, 비대화형 선택은 init --help. '
                           '데이터셋은 직접 선택하며 모델 없는 합성 예제는 README.md를 참고하세요.'))
dataset_app = typer.Typer(help="데이터셋 목록 표시 및 명시적으로 선택한 데이터셋 준비", no_args_is_help=True)
app.add_typer(dataset_app, name="datasets")
catalog_app = typer.Typer(help="준비·모델 호출 없이 등록된 네 구성요소 조회", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")


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
    if spec.get("preset_selection"):
        from agent_optimizer.preset_tui import verify_ace_selection
        verify_ace_selection(spec)
        return None
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
    api = research or any((profile["adapter"] not in {"opencode", "ace_opencode"} or
                           profile["adapter"] == "ace_opencode" and not spec.get("preset_selection")) and
                          model_keys.issubset(profile.get("runtime", {}).get("env_passthrough", []))
                          for profile in profiles)
    staged = dict(os.environ if env is None else env)
    if api:
        staged = ensure_model_api(staged)
    for profile in profiles:
        if (profile["adapter"] == "opencode" or
                profile["adapter"] == "ace_opencode" and spec.get("preset_selection")):
            selector = profile.get("model_env", "AGENT_OPT_MODEL")
            staged = ensure_model_selector(staged, selector)
            if (profile["adapter"] == "ace_opencode" and spec.get("preset_selection")
                    and staged[selector].startswith("compatible/") and not api):
                staged = ensure_model_api(staged)
    return staged


def _recent_configurations(project_root: Path) -> list[Path]:
    """List only generated experiment files, without following configuration symlinks."""
    base = project_root / "runs" / "configs"
    if (project_root / "runs").is_symlink() or base.is_symlink() or not base.is_dir():
        return []
    entries = []
    for path in base.rglob("experiment.toml"):
        relative = path.relative_to(base)
        if path.is_symlink() or any((base / Path(*relative.parts[:index])).is_symlink()
                                   for index in range(1, len(relative.parts))):
            continue
        try:
            if path.is_file() and path.resolve().is_relative_to(base.resolve()):
                entries.append((path.stat().st_mtime_ns, str(path), path))
        except OSError:
            continue
    entries.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [path for _, _, path in entries[:5]]


def _history_run(runs_fd: int, parent: str, name: str) -> tuple[str, float] | None:
    """Check a recorded run through directory-relative, non-following file descriptors."""
    match = re.fullmatch(r"([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{8}", name)
    if match is None:
        return None
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        created = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        with contextlib.ExitStack() as opened:
            parent_fd = runs_fd
            if parent:
                parent_fd = os.open(parent, directory_flags, dir_fd=runs_fd)
                opened.callback(os.close, parent_fd)
            run_fd = os.open(name, directory_flags, dir_fd=parent_fd)
            opened.callback(os.close, run_fd)
            with os.fdopen(os.open("summary.json", file_flags, dir_fd=run_fd), encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    return None
                summary = json.loads(stream.read(16 * 1024 * 1024 + 1))
            with os.fdopen(os.open("report.html", file_flags, dir_fd=run_fd), "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    return None
            if (not isinstance(summary, dict) or type(summary.get("schema_version")) is not int
                    or summary["schema_version"] != 1 or summary.get("run_id") != name
                    or not isinstance(summary.get("status"), str)
                    or summary["status"] not in {"running", "completed", "partial",
                                                 "no_eligible_candidate", "interrupted",
                                                 "budget_exhausted", "source_error", "error"}
                    or not isinstance(summary.get("groups"), list)
                    or type(summary.get("trials_used")) is not int or summary["trials_used"] < 0):
                return None
            return summary["status"], created.timestamp()
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None


def _tui_run_history(project_root: Path) -> int | None:
    runs = project_root.absolute() / "runs"
    found = []
    try:
        runs_fd = os.open(runs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        print(human("실행 기록이 없습니다."), file=sys.stderr)
        return 0
    with contextlib.ExitStack() as opened:
        opened.callback(os.close, runs_fd)
        for parent in ("", "dev-live"):
            try:
                parent_fd = runs_fd if not parent else os.open(
                    parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=runs_fd)
            except OSError:
                continue
            try:
                with os.scandir(parent_fd) as children:
                    for child in children:
                        if child.name == "configs" or (not parent and child.name == "dev-live"):
                            continue
                        recorded = _history_run(runs_fd, parent, child.name)
                        if recorded is not None:
                            found.append((recorded[1], parent, child.name, recorded[0]))
            finally:
                if parent:
                    os.close(parent_fd)
    found.sort(key=lambda row: (-row[0], row[1], row[2]))
    found = found[:10]
    if not found:
        print(human("실행 기록이 없습니다."), file=sys.stderr)
        return 0
    for number, (_, parent, name, status) in enumerate(found, 1):
        report = runs / parent / name / "report.html"
        print(f"{number}. {name} · {status} · {report}", file=sys.stderr)
    print(human("실행 번호 (0: 돌아가기): "), end="", file=sys.stderr, flush=True)
    choice = input().strip()
    if choice == "0":
        return None
    if not choice.isascii() or not choice.isdecimal() or not 1 <= int(choice) <= len(found):
        raise ConfigurationError(human("목록의 실행 번호를 선택하세요"))
    _, parent, name, status = found[int(choice) - 1]
    try:
        runs_fd = os.open(runs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise ConfigurationError(human("보고서를 안전하게 확인할 수 없습니다")) from None
    try:
        recorded = _history_run(runs_fd, parent, name)
    finally:
        os.close(runs_fd)
    if recorded is None or recorded[0] != status:
        raise ConfigurationError(human("보고서를 안전하게 확인할 수 없습니다"))
    print(f"{human('보고서 경로')}: {runs / parent / name / 'report.html'}", file=sys.stderr)
    return 0


def _run_ace_selection(project_root: Path, optimizer: str) -> int:
    """사용자 확인 후에만 고정 자산 준비, 설정 작성, 진단, 실제 실행을 순서대로 수행한다."""
    from agent_optimizer.preset_tui import ACE_GUIDANCE, ACE_SCAFFOLD, _tr, write_ace_selection
    from agent_optimizer.registry import is_source_checkout

    root = project_root.absolute()
    if not is_source_checkout(root):
        print(human("ACE-RTL 작업공간 경로: "), end="", file=sys.stderr, flush=True)
        entered = input().strip()
        if not entered:
            raise ConfigurationError(human("ACE-RTL 작업공간 경로를 입력하세요"))
        root = Path(entered).expanduser().absolute()
    maximum = 1 if optimizer == "baseline" else 9
    changed = (_tr("변경 없음", "no changes") if optimizer == "baseline" else
               ACE_GUIDANCE if optimizer == "gepa" else ACE_SCAFFOLD)
    def model_status(key):
        return (_tr("설정됨", "configured") if os.environ.get(key) else
                _tr("입력 필요", "input needed"))
    agent_model = os.environ.get("AGENT_OPT_MODEL", "")
    agent_key = ("OPENROUTER_API_KEY" if agent_model.startswith("openrouter/") else
                 "AGENT_OPT_MODEL_API_KEY" if agent_model.startswith("compatible/") else None)
    agent_key_status = (f" · {agent_key}: {model_status(agent_key)}" if agent_key else
                        f" · {_tr('선택 후 provider 인증 확인', 'check provider credentials after selection')}")
    optimizer_model = (_tr("필요 없음", "not needed") if optimizer == "baseline" else
                       f"AGENT_OPT_MODEL_BASE_URL: {model_status('AGENT_OPT_MODEL_BASE_URL')} · "
                       f"AGENT_OPT_MODEL_ID: {model_status('AGENT_OPT_MODEL_ID')} · "
                       f"{_tr('API 키', 'API key')}: {model_status('AGENT_OPT_MODEL_API_KEY')}")
    print(f"\nAgent: ACE-RTL ({_tr('고정 Git commit · 스킬 프로필', 'pinned Git commit · skill profile')})\n"
          f"Harness: OpenCode (ace-opencode / ace_opencode)\n"
          f"Optimizer: {optimizer} · {_tr('이번 수정 파일', 'file to edit')}: {changed}\n"
          f"Dataset: CVDP · {_tr('공식', 'official')} evaluator=cvdp · train 1 / validation 1 · final_test=false\n"
          f"{_tr('수정 가능 파일', 'Editable files')}: SKILL.md, role-guidance.md, Python scripts\n"
          f"{_tr('Agent 모델', 'Agent model')}: AGENT_OPT_MODEL {model_status('AGENT_OPT_MODEL')}"
          f"{agent_key_status}\n"
          f"{_tr('Optimizer 모델', 'Optimizer model')}: {optimizer_model}\n"
          f"{_tr('준비 작업', 'Preparation')}: "
          f"{_tr('고정 Git/CVDP 데이터·driver·Docker 이미지 (확인 후에만 수행)', 'pinned Git/CVDP data, driver, Docker images (only after confirmation)')}\n"
          f"{_tr('예산', 'Budget')}: {_tr('최대', 'up to')} {maximum} trial / "
          f"{_tr('최대', 'up to')} {maximum * 600 + 360}{_tr('초', ' seconds')} · "
          f"{_tr('trial당 600초', '600 seconds per trial')}\n"
          f"{_tr('설정', 'Configuration')}: {root / 'runs/configs/<new-config>/experiment.toml'}\n"
          f"{_tr('보고서', 'Report')}: {root / 'runs/<run-id>/report.html'}\n"
          f"{_tr('평가 의미: 선택된 공개 validation 과제, 최종 test 없음', 'Evaluation: selected public validation task; no final test')}", file=sys.stderr)
    print(_tr("준비하고 실행할까요? [y/N/b: 이전]: ",
              "Prepare and run? [y/N/b: back]: "), end="", file=sys.stderr, flush=True)
    answer = input().strip().lower()
    if answer == "b":
        return -1
    if answer not in {"y", "yes"}:
        print(human("실험 준비를 취소했습니다"), file=sys.stderr)
        return 2
    from agent_optimizer.preset_tui import prepare_ace_selection, run_ace_selection
    prepare_ace_selection(root)
    experiment = write_ace_selection(root, optimizer)
    spec = load_experiment(experiment)
    from agent_optimizer.model_input import session_environment
    with session_environment(_tui_model_environment(spec)):
        return run_ace_selection(experiment)


def _run_sample_selection(project_root: Path, agent_id: str, optimizer: str) -> int:
    """합성 fixture 조합의 확인 및 기존 plan/run 경로."""
    from agent_optimizer.preset_tui import _tr
    root = project_root.absolute()
    maximum = 4 if optimizer == "file_variants" else 3
    print(f"\nAgent: {agent_id} ({_tr('로컬 합성 예제', 'local synthetic fixture')})\n"
          f"Harness: Fixture ({_tr('모델 호출 없음', 'no model call')})\n"
          f"Optimizer: {optimizer} · "
          f"{'configs/strategy.json' if optimizer == 'file_variants' else _tr('변경 없음', 'no changes')}\n"
          f"Dataset: sample_text · evaluator=sample_eval · train/validation/test · "
          f"{_tr('합성 평가', 'synthetic evaluation')}\n"
          f"{_tr('Agent/Optimizer 모델: 필요 없음', 'Agent/Optimizer models: not needed')}\n"
          f"{_tr('준비 작업: 로컬 예제 파일 검사', 'Preparation: inspect local fixture files')}\n"
          f"{_tr('예산', 'Budget')}: {_tr('최대', 'up to')} {maximum} trial / 3600{_tr('초', ' seconds')} · "
          f"{_tr('trial당 120초', '120 seconds per trial')}\n"
          f"{_tr('설정', 'Configuration')}: {root / 'runs/configs/<new-config>/experiment.toml'}\n"
          f"{_tr('보고서', 'Report')}: {root / 'runs/<run-id>/report.html'}", file=sys.stderr)
    print(_tr("준비하고 실행할까요? [y/N/b: 이전]: ", "Prepare and run? [y/N/b: back]: "),
          end="", file=sys.stderr, flush=True)
    answer = input().strip().lower()
    if answer == "b":
        return -1
    if answer not in {"y", "yes"}:
        print(human("실험 준비를 취소했습니다"), file=sys.stderr)
        return 2
    from agent_optimizer.preset_tui import write_sample_selection
    experiment = write_sample_selection(root, agent_id, optimizer)
    report = collect_plan(experiment, Registry())
    if not report["ready"]:
        problems = ", ".join(row["id"] for row in report["checks"] if row["status"] != "ok")
        raise ConfigurationError("합성 실험 정적 진단 실패: " + problems)
    return main(["run", str(experiment)])


@app.command("plugins")
def plugins_command(project_root: Path | None = None) -> int:
    """구현된 연동 목록 표시."""
    return _invoke("plugins", project_root=project_root or Path.cwd())


@catalog_app.command("list")
def catalog_list(kind: str = typer.Option(..., "--kind", help="agent|harness|optimizer|dataset"),
                 project_root: Path | None = None,
                 json_output: bool = typer.Option(False, "--json", help="단일 JSON 목록")) -> int:
    """구현된 구성요소와 준비 상태 조회(읽기 전용)."""
    return _invoke("catalog", kind=kind, identifier=None, project_root=project_root or Path.cwd(),
                   json=json_output)


@catalog_app.command("show")
def catalog_show(kind: str, identifier: str, project_root: Path | None = None,
                 json_output: bool = typer.Option(False, "--json", help="단일 JSON 객체")) -> int:
    """등록 ID의 역할·제약과 준비 조건 표시(읽기 전용)."""
    return _invoke("catalog", kind=kind, identifier=identifier,
                   project_root=project_root or Path.cwd(), json=json_output)


@app.command("prepare")
def prepare_command(experiment: Path, offline: bool = False) -> int:
    """선택한 ACE/CVDP 고정 자산 준비·재사용(다운로드·Docker 빌드 가능)."""
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
                  agent_preset: str | None = typer.Option(None, "--agent-preset", help="등록된 Agent 프리셋 ID(--agent와 배타)"),
                  harness_profile: str | None = typer.Option(None, "--harness-profile", help="전용 Harness 프로필 ID(--harness와 배타)"),
                 revision: str | None = None, name: str | None = None,
                 command: str | None = typer.Option(None, "--command", help="명령 하네스의 Agent argv: 인용을 분리하지만 셸 확장·파이프·리다이렉션은 실행하지 않음"),
                 editable: list[str] | None = typer.Option(None, "--editable", help="수정 허용 Agent 경로/패턴(반복 가능)"),
                 prompt_file: str = "prompts/system.md",
                 dataset: list[str] | None = typer.Option(None, "--dataset", help="데이터셋 직접 선택: 등록 ID 또는 로컬 tasks.json(반복 가능)"),
                 evaluator: str | None = None, metric: str = "passed",
                 direction: Literal["maximize", "minimize"] = typer.Option("maximize", "--direction"),
                  harness: str | None = typer.Option(None, "--harness", help="일반 Harness adapter ID(기본 command; --harness-profile과 배타)"), optimizer: list[str] | None = typer.Option(None, "--optimizer", help="명시적으로 선택할 Optimizer ID(필수, 반복 가능; 예: baseline)"),
                 optimizer_config: str | None = None, scaffold_file: str | None = None,
                 target_file: str | None = None, max_tasks: int = 9, max_trials: int | None = None,
                  max_wall_time_seconds: float | None = None,
                  trial_timeout_seconds: float | None = None,
                 offline: bool = False,
                  yes: bool = typer.Option(False, help="선택 데이터·고정 소스 다운로드/Docker 빌드 가능성을 승인")) -> int:
    """Agent 경로/프리셋 설정 생성; --yes는 선택 자산 준비를 승인합니다."""
    if profile is not None or workspace is not None:
        if agent_preset or harness_profile:
            raise typer.BadParameter("--profile/--workspace와 프리셋 선택은 섞을 수 없습니다")
        return _invoke("init-profile", profile=profile, workspace=workspace, agent=agent,
                       dataset=dataset, evaluator=evaluator, optimizer=optimizer, editable=editable,
                       command_text=command, revision=revision, name=name)
    if (not any((agent, agent_preset, harness_profile, dataset, editable, command, name, revision, optimizer))
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
        print(f"{human('설정 생성')}: {prepared.get('experiment') or prepared['session']}", file=sys.stderr)
        return 0
    return _invoke("init", project_root=project_root or Path.cwd(), agent=agent,
                    agent_preset=agent_preset, harness_profile=harness_profile,
                   revision=revision, name=name, command_text=command,
                   editable=editable, prompt_file=prompt_file, dataset=dataset,
                   evaluator=evaluator, metric=metric, direction=direction,
                    harness=harness or "command", explicit_harness=harness is not None,
                    optimizer=optimizer, optimizer_config=optimizer_config,
                   scaffold_file=scaffold_file, target_file=target_file, max_tasks=max_tasks,
                    max_trials=max_trials, max_wall_time_seconds=max_wall_time_seconds,
                    trial_timeout_seconds=trial_timeout_seconds, offline=offline, yes=yes)


@app.command("tui")
def tui_command(project_root: Path | None = None) -> int:
    """기존 실험·새 실험 실행 또는 이전 실행 보기(TTY 필요)."""
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
    """준비된 실험 실행 및 보고서 작성(후보·Harness·평가기 외부 호출 가능)."""
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
        if args.command == "catalog":
            result = (describe_choice(args.kind, args.identifier, args.project_root)
                      if args.identifier else list_choices(args.kind, args.project_root))
            if args.json:
                show(result)
            else:
                for row in result if isinstance(result, list) else [result]:
                    print(f"{row['name']} [{row['id']}] · " +
                          human("준비 확인 필요" if not row["ready"] else "등록됨"))
                    print("  " + human(row["description"]))
                    if args.identifier:
                        if row["requirements"]:
                            print(f"  {human('필요')}: " + ", ".join(row["requirements"]))
                        if row["supported_with"]:
                            print(f"  {human('조합')}: " + ", ".join(row["supported_with"]))
                        print(f"  {human('범위')}: " + human(row["reason"]))
        elif args.command == "plugins":
            registry.load_project(args.project_root.absolute())
            show(registry.describe())
        elif args.command == "prepare":
            from agent_optimizer.integrations import prepare_experiment
            print(human("ACE 준비: 고정 소스·데이터·driver 및 Docker 이미지 준비/재사용"), file=sys.stderr)
            show(prepare_experiment(args.experiment, offline=args.offline))
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
            next_command(f"agent-opt prepare {shlex.quote(str(target))}")
        elif args.command == "init":
            if args.agent_preset or args.harness_profile:
                from agent_optimizer.config import identifier, positive
                from agent_optimizer.preset_tui import (ACE_GUIDANCE, ACE_SCAFFOLD,
                    ace_stage_config, prepare_ace_selection, write_ace_selection,
                    write_sample_selection)
                if args.agent or args.revision or args.editable or args.command_text or args.explicit_harness:
                    raise ConfigurationError("--agent/--harness 경로 입력과 프리셋 선택은 배타적입니다")
                if not args.agent_preset or not args.harness_profile:
                    raise ConfigurationError("--agent-preset과 --harness-profile을 함께 지정하세요")
                if not args.name:
                    raise ConfigurationError("프리셋 설정에는 --name이 필요합니다")
                identifier(args.name)
                root = args.project_root.absolute()
                folder = root / "runs/configs" / args.name
                if (root / "runs").is_symlink() or (root / "runs/configs").is_symlink():
                    raise ConfigurationError("실험 설정 디렉터리는 symlink일 수 없습니다")
                if folder.exists() or folder.is_symlink():
                    raise ConfigurationError(f"Generated configuration already exists: {folder}")
                try:
                    configs = json.loads(args.optimizer_config) if args.optimizer_config else {}
                except json.JSONDecodeError as exc:
                    raise ConfigurationError(f"--optimizer-config JSON 오류: {exc.msg}") from exc
                if not isinstance(configs, dict) or not all(
                        isinstance(key, str) and isinstance(value, dict)
                        for key, value in configs.items()):
                    raise ConfigurationError("--optimizer-config는 Optimizer ID → 옵션 JSON 객체여야 합니다")
                if args.evaluator or args.metric != "passed" or args.direction != "maximize":
                    raise ConfigurationError("프리셋은 등록된 평가기와 passed/maximize 지표를 사용합니다")
                if args.prompt_file != "prompts/system.md":
                    raise ConfigurationError("프리셋은 원본 Agent의 prompt_file을 사용합니다")
                if args.trial_timeout_seconds is not None:
                    positive(args.trial_timeout_seconds, "trial_timeout_seconds")
                if args.max_wall_time_seconds is not None:
                    positive(args.max_wall_time_seconds, "max_wall_time_seconds")
                optimizers, datasets = args.optimizer or [], args.dataset or []
                if (args.agent_preset == "ace-rtl" and args.harness_profile == "ace-opencode"
                        and datasets == ["cvdp"] and len(optimizers) == 1
                        and optimizers[0] in {"gepa", "meta_harness"}):
                    optimizer = optimizers[0]
                    if (args.max_tasks not in {2, 9}
                            or args.target_file and (optimizer != "gepa" or args.target_file != ACE_GUIDANCE)
                            or args.scaffold_file and (optimizer != "meta_harness" or
                                                       args.scaffold_file != ACE_SCAFFOLD)):
                        raise ConfigurationError("ACE 프리셋의 공개 두 과제와 활성 수정 파일을 확인하세요")
                    if set(configs) - {optimizer}:
                        raise ConfigurationError("--optimizer-config는 선택한 Optimizer만 지정하세요")
                    options = ace_stage_config(optimizer, configs.get(optimizer))
                    minimum = 3 + 2 * options["iterations"]
                    if args.max_trials is not None and args.max_trials < minimum:
                        raise ConfigurationError(f"ACE 프리셋 max_trials는 최소 {minimum}이어야 합니다")
                elif (args.agent_preset in {"rtl-solo", "rtl-team"} and
                      args.harness_profile == "fixture" and datasets == ["sample_text"] and
                      len(optimizers) == 1 and optimizers[0] in {"baseline", "file_variants"}):
                    optimizer = optimizers[0]
                    if (configs or args.target_file or args.scaffold_file or args.max_tasks not in {3, 9}):
                        raise ConfigurationError("합성 프리셋은 등록된 fixture 파일·예산을 사용합니다")
                    minimum = 3 + (optimizer == "file_variants")
                    if args.max_trials is not None and args.max_trials < minimum:
                        raise ConfigurationError(f"합성 프리셋 max_trials는 최소 {minimum}이어야 합니다")
                else:
                    raise ConfigurationError("지원하지 않는 프리셋 조합입니다; "
                                             "agent-opt catalog list --kind harness")
                if not args.yes:
                    raise ConfigurationError("선택 자산의 다운로드·빌드를 승인하려면 --yes를 지정하세요")
                if args.agent_preset == "ace-rtl":
                    print(human("ACE 준비: 고정 소스·데이터·driver 및 Docker 이미지 준비/재사용"),
                          file=sys.stderr)
                    prepare_ace_selection(root, offline=args.offline)
                    target = write_ace_selection(root, optimizer, name=args.name, options=configs.get(optimizer),
                                                 max_trials=args.max_trials,
                                                 wall_time=args.max_wall_time_seconds,
                                                 trial_timeout=args.trial_timeout_seconds)
                else:
                    target = write_sample_selection(root, args.agent_preset, optimizer, name=args.name,
                                                    max_trials=args.max_trials,
                                                    wall_time=args.max_wall_time_seconds,
                                                    trial_timeout=args.trial_timeout_seconds)
                spec = load_experiment(target)
                show({"experiment": str(target), "dataset": datasets[0],
                      "stages": [stage["id"] for stage in spec.get("stages", [])]})
                if args.agent_preset == "ace-rtl":
                    next_command(f"agent-opt prepare {shlex.quote(str(target))}")
                next_command(f"agent-opt doctor --plan {shlex.quote(str(target))} --json")
                next_command(f"agent-opt plan {shlex.quote(str(target))}")
                next_command(f"agent-opt run {shlex.quote(str(target))}")
                return 0
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
            git_source = ("://" in args.agent or
                          bool(re.fullmatch(r"(?:[\w.-]+@)?[\w.-]+:[^\s]+", args.agent)))
            if git_source and not args.revision:
                raise ConfigurationError("A pinned Git Agent requires a revision")
            if args.revision is not None:
                validate_source(SourceSpec(kind="git", url=args.agent, revision=args.revision))
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
                                                  wall_time=(args.max_wall_time_seconds if
                                                             args.max_wall_time_seconds is not None else 3600),
                                                  trial_timeout=(args.trial_timeout_seconds if
                                                                 args.trial_timeout_seconds is not None else 120),
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
                    for item in experiments:
                        next_command(f"agent-opt doctor --plan {shlex.quote(item['experiment'])}")
                    next_command(f"agent-opt run-session {shlex.quote(str(target))}")
                else:
                    show({"experiment": experiments[0]["experiment"], "dataset": args.dataset[0],
                          "stages": [s["id"] for s in stages]})
                    next_command(f"agent-opt doctor --plan {shlex.quote(experiments[0]['experiment'])}")
                    next_command(f"agent-opt run {shlex.quote(experiments[0]['experiment'])}")
                rollback.pop_all()
        elif args.command == "tui":
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                from agent_optimizer.preset_tui import _tr
                raise ConfigurationError(t("TUI requires a TTY for both input and output") + "; " +
                                         _tr("자동화에는 agent-opt init과 agent-opt run을 사용하세요",
                                             "Use agent-opt init and agent-opt run for noninteractive automation"))
            try:
                while True:
                    print("\n" + human("실험 시작: 5. 프리셋 선택형 새 최적화  1. 기존 실험 실행  2. 고급 새 실험 만들고 실행  3. ACE-RTL + CVDP 예제  4. 이전 실행 보기"), file=sys.stderr)
                    print(human("선택 [5/1/2/3/4]: "), end="", file=sys.stderr, flush=True)
                    choice = input().strip()
                    if choice == "5":
                        from agent_optimizer.preset_tui import select_four
                        previous = None
                        while choice == "5":
                            selected = (select_four(args.project_root.absolute(), initial=previous,
                                                    start_page=3) if previous else
                                        select_four(args.project_root.absolute()))
                            if selected is None:
                                return 2
                            if selected[0] == "custom":
                                choice = "2"
                            elif selected[0] == "existing":
                                choice = "1"
                            else:
                                result = (_run_sample_selection(args.project_root, selected[0], selected[2])
                                          if selected[0] in {"rtl-solo", "rtl-team"} else
                                          _run_ace_selection(args.project_root, selected[2]))
                                if result != -1:
                                    return result
                                previous = selected
                    if choice != "4":
                        break
                    history = _tui_run_history(args.project_root)
                    if history is not None:
                        return history
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
                        recent = _recent_configurations(args.project_root)
                        if recent:
                            print(human("최근 생성된 실험 설정 (번호 또는 경로 직접 입력):"), file=sys.stderr)
                            for index, path in enumerate(recent, 1):
                                print(f"  {index}. {path}", file=sys.stderr)
                        else:
                            print(human("최근 생성 설정이 없습니다. 경로를 직접 입력하세요."), file=sys.stderr)
                        print(human("기존 experiment.toml 경로: "), end="", file=sys.stderr, flush=True)
                        selected = input().strip()
                        if not selected:
                            raise ConfigurationError(human("실험 설정 경로를 입력하세요"))
                        if selected.lstrip("+-").isdecimal():
                            if not selected.isdecimal() or not 1 <= int(selected) <= len(recent):
                                raise ConfigurationError(human("목록의 설정 번호를 선택하세요"))
                            experiment = recent[int(selected) - 1]
                        else:
                            experiment = Path(selected).expanduser()
                        if not experiment.is_absolute():
                            experiment = args.project_root / experiment
                        experiment = experiment.resolve()
                    init_args = None
                elif choice == "2":
                    init_args = wizard_arguments(args.project_root.absolute())
                else:
                    raise ConfigurationError(human("1, 2, 3, 4 또는 5를 선택하세요"))
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
                    if spec.get("preset_selection"):
                        _launch_existing(spec, registry)
                        return main(["run", str(spec["_source"])])
                    launched = _launch_existing(spec, registry)
                    if launched is not None:
                        return launched
                    with ProgressDisplay() as progress:
                        progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                        root, summary = run_experiment(spec, Registry(), on_event=progress)
                    show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"],
                          "report_html": root / "report.html"})
                    print(f"{human('결과 HTML')}: {root / 'report.html'}", file=sys.stderr)
                    next_command(f"agent-opt report {shlex.quote(str(root))}")
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
            print(f"{human('결과 HTML')}: {index}", file=sys.stderr)
            for entry in entries:
                if entry["report"]:
                    next_command(f"agent-opt report {shlex.quote(str((session_root / entry['report']).parent))}")
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
                    if args.plan:
                        if args.model:
                            print(human("--model은 모델 API 연결을 호출하지만 Agent 실행 성공은 확인하지 않습니다."),
                                  file=sys.stderr)
                        else:
                            print(human("계획 진단은 정적 검사입니다. Agent·채점기·모델 실행은 확인하지 않았습니다."),
                                  file=sys.stderr)
                return 0 if report["ready"] else 2
            raise ConfigurationError("agent-opt doctor --plan PATH 또는 --dataset ID를 지정하세요")
        elif args.command == "agents":
            show([load_agent(p) for p in sorted(args.root.rglob("agent.toml"))])
        elif args.command in {"plan", "run"}:
            spec = load_experiment(args.experiment.resolve())
            if args.command == "run":
                if spec.get("preset_selection"):
                    _launch_existing(spec, registry, output=args.output)
                    if args.output is not None:
                        raise ConfigurationError("ACE 선택형 실행은 별도 --output을 지원하지 않습니다")
                    from agent_optimizer.preset_tui import run_ace_selection
                    return run_ace_selection(spec["_source"])
                launched = _launch_existing(spec, registry, output=args.output)
                if launched is not None:
                    return launched
                with ProgressDisplay() as progress:
                    progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                    root, summary = run_experiment(spec, registry, args.output, on_event=progress)
                show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"],
                      "report_html": root / "report.html"})
                print(f"{human('결과 HTML')}: {root / 'report.html'}", file=sys.stderr)
                next_command(f"agent-opt report {shlex.quote(str(root))}")
                return 0 if summary["status"] == "completed" else 3
            available, detail = True, ""
            try:
                preflight(spec, registry)
            except UnavailableError as exc:
                available, detail = False, str(exc)
            show({"valid": True, "integrations_ready": available, "detail": detail,
                  "matrix": [{"agent": a.id, "harness": h["id"]} for a, h in selected_pairs(spec)],
                  "sources": {a.id: a.source for a in spec["_agents"]},
                  "stages": spec.get("stages", []), "objective": spec["objective"],
                  "tasks_by_split": {s: sum(t.split == s for t in spec["_tasks"]) for s in ["train", "validation", "test"]},
                   "note": "Schema/registry validation only. Run doctor and environment checks before real execution."})
            print(human("정적 계획 확인; 실행 성공 아님"), file=sys.stderr)
            next_command(f"agent-opt doctor --plan {shlex.quote(str(args.experiment))}")
        elif args.command == "report":
            data = json.loads((args.run_dir / "summary.json").read_text())
            if args.html:
                from agent_optimizer.results import write_report_artifacts
                with PreparationStatus("html", action="report", subject="check"):
                    language = report_language(data, args.run_dir,
                                               override=os.environ.get("AGENT_OPT_LANG") or None)
                    target = write_report_artifacts(args.run_dir, data, language=language)
                show({"html": target, "status": data["status"]})
                print(f"{human('결과 HTML')}: {target}", file=sys.stderr)
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
            print(f"{human('결과 HTML')}: {args.run_dir / 'report.html'}", file=sys.stderr)
            print(human("저장된 자료로 재생성할 때만"), file=sys.stderr)
            next_command(f"agent-opt report {shlex.quote(str(args.run_dir))} --html")
    except (ConfigurationError, UnavailableError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"{style('error:', 'error', stream=sys.stderr)} {human(str(exc))}", file=sys.stderr)
        return 2
    return 0
