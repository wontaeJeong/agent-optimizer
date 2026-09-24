from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from agent_optimizer.config import load_agent, load_experiment
from agent_optimizer.contracts import ConfigurationError, UnavailableError, jsonable
from agent_optimizer.runner import preflight, run_experiment
from agent_optimizer.registry import Registry
from agent_optimizer.network import network_environment
from agent_optimizer.setup_wizard import (component_inventory, prepare_selection,
                                          _bounded_tasks, choose_editable_file, wizard_arguments,
                                          write_experiment)
from agent_optimizer.terminal_report import ProgressDisplay
from agent_optimizer.terminal_style import ColorArgumentParser, style
from agent_optimizer.results import write_json
from agent_optimizer.readiness import collect_dataset, collect_plan


def show(value):
    print(json.dumps(jsonable(value), indent=2, ensure_ascii=False, allow_nan=False))


def doctor():
    result = {}
    for binary, flag in [("python3", "--version"), ("git", "--version"), ("docker", "--version"), ("opencode", "--version")]:
        path = shutil.which(binary)
        row = {"available": bool(path), "path": path}
        if path:
            try:
                proc = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
                row["version"] = (proc.stdout or proc.stderr).splitlines()[:2]
            except (OSError, subprocess.TimeoutExpired) as exc:
                row["error"] = str(exc)
        result[binary] = row
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "doctor":
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            return _main(argv)
        finally:
            sys.dont_write_bytecode = previous
    return _main(argv)


def _main(argv):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "rerank":
        print(style("error:", "error", stream=sys.stderr) + " rerank is deferred; configure the objective for a new run. "
              "Stored reports and frozen selections remain available; see deferred/README.md", file=sys.stderr)
        return 2
    parser = ColorArgumentParser(
        description="여러 Agent의 최적화 실험을 위한 작업 도구",
        epilog=('저장소에서 시작: make setup ARGS="--core" 후 agent-opt datasets list로 '
                '데이터셋을 확인하세요. 대화형은 agent-opt tui(TTY 필요), 비대화형은 '
                'agent-opt init --help를 사용합니다. 모델 없는 합성 예제는 README.md를 참고하세요.'))
    sub = parser.add_subparsers(dest="command", required=True)
    plugins = sub.add_parser("plugins", help="구현된 연동 목록 표시")
    plugins.add_argument("--project-root", type=Path, default=Path.cwd(), help="저장소 루트(기본값: 현재 디렉터리)")
    diagnostic = sub.add_parser(
        "doctor", help="도구·선택 데이터셋·실험 계획의 준비 상태 진단",
        description=("기본 동작은 도구 목록 확인입니다. --dataset ID와 --plan PATH는 설치·Agent 실행·"
                     "모델 호출 없이 읽기 전용으로 점검합니다. --model에는 --plan 필요; 모델 API를 호출합니다."))
    selected = diagnostic.add_mutually_exclusive_group()
    selected.add_argument("--dataset", metavar="ID", help="선택한 등록 데이터셋 하나 진단(읽기 전용)")
    selected.add_argument("--plan", type=Path, metavar="PATH", help="준비된 experiment.toml 진단(읽기 전용)")
    diagnostic.add_argument("--project-root", type=Path, default=Path.cwd(), help="--dataset의 저장소 루트(기본값: 현재 디렉터리)")
    diagnostic.add_argument("--json", action="store_true", help="기계가 읽을 수 있는 단일 진단 결과 출력")
    diagnostic.add_argument("--model", action="store_true", help="--plan 필요; 모델 API를 명시적으로 호출")
    datasets = sub.add_parser("datasets", help="데이터셋 목록 표시 및 명시적으로 선택한 데이터셋 준비")
    dataset_actions = datasets.add_subparsers(dest="dataset_action", required=True)
    for action in ("list", "prepare"):
        item = dataset_actions.add_parser(
            action, help=("등록 데이터셋 목록 표시" if action == "list" else "직접 선택한 데이터셋 준비"))
        item.add_argument("--project-root", type=Path, default=Path.cwd(), help="저장소 루트(기본값: 현재 디렉터리)")
        if action == "prepare":
            item.add_argument("name", nargs="?", help="등록된 데이터셋 ID 또는 로컬 tasks.json")
            item.add_argument("--evaluator", help="로컬 tasks.json에는 필수: file.py:Symbol")
            item.add_argument("--offline", action="store_true", help="검증된 캐시 자산만 재사용")
    init = sub.add_parser("init", help="직접 선택한 데이터셋으로 실험 설정 생성",
                          description="로컬 또는 고정 커밋의 Git Agent와 선택한 데이터셋으로 실험을 준비합니다.")
    init.add_argument("--project-root", type=Path, default=Path.cwd(), help="저장소 루트(기본값: 현재 디렉터리)")
    init.add_argument("--agent", help="로컬 소스 경로 또는 Git URL(Git이면 --revision 지정)")
    init.add_argument("--revision", help="Git Agent에 필요한 전체 커밋 해시")
    init.add_argument("--name", help="실험 이름; 설정은 runs/configs/에 생성")
    init.add_argument("--argv", nargs="+", help="Agent 실행 인수; {python}, {agent_dir}, {task_dir} 사용")
    init.add_argument("--command-json", help="대시(-)로 시작하는 Agent 옵션을 포함할 수 있는 JSON 인수 배열")
    init.add_argument("--editable", action="append", help="수정 허용 Agent 경로/패턴(반복 가능)")
    init.add_argument("--prompt-file", default="prompts/system.md", help="Agent 프롬프트 경로(기본값: prompts/system.md)")
    init.add_argument("--dataset", action="append", help="데이터셋을 직접 선택: 등록 ID 또는 로컬 tasks.json(반복 가능)")
    init.add_argument("--evaluator", help="로컬 tasks.json에는 필수: file.py:Symbol")
    init.add_argument("--metric", default="passed", help="평가기 지표 이름(기본값: passed)")
    init.add_argument("--direction", choices=("maximize", "minimize"), default="maximize")
    init.add_argument("--harness", default="command", help="등록된 Harness ID(기본값: command)")
    init.add_argument("--optimizer", action="append", help="등록된 Optimizer ID(반복 가능; 기본값: gepa)")
    init.add_argument("--optimizer-config", help="Optimizer ID별 옵션의 JSON 매핑")
    init.add_argument("--scaffold-file", help="Meta-Harness/Ecdysis의 수정 허용 Python 파일")
    init.add_argument("--target-file", help="연구 Optimizer가 수정할 정확한 텍스트 파일")
    init.add_argument("--max-tasks", type=int, default=9, help="데이터셋별 최대 과제 수(기본값: 9)")
    init.add_argument("--max-trials", type=int, help="최대 trial 예산")
    init.add_argument("--max-wall-time-seconds", type=float, default=3600, help="실행 시간 제한(초, 기본값: 3600)")
    init.add_argument("--trial-timeout-seconds", type=float, default=120, help="trial별 시간 제한(초, 기본값: 120)")
    init.add_argument("--offline", action="store_true", help="검증된 데이터셋 캐시만 재사용")
    init.add_argument("--yes", action="store_true", help="TTY 없이 준비를 확인하고 진행")
    tui = sub.add_parser("tui", help="대화형 설정 및 실행 진행 상황 표시",
                         description="TTY 필요. 실행 전 Agent, 수정 허용 파일, 데이터셋을 직접 선택합니다.")
    tui.add_argument("--project-root", type=Path, default=Path.cwd(), help="저장소 루트(기본값: 현재 디렉터리)")
    session = sub.add_parser("run-session", help="선택한 데이터셋마다 독립 평가기로 실행")
    session.add_argument("session", type=Path, help="여러 --dataset으로 init이 생성한 session.json")
    session.add_argument("--output", type=Path, help="세션 결과 디렉터리 지정")
    agents = sub.add_parser("agents", help="독립 등록된 Agent 대상 목록 표시")
    agents.add_argument("--root", type=Path, default=Path("examples"), help="Agent 선언 디렉터리(기본값: examples)")
    for name, description in (("validate", "준비된 실험 설정과 연동 계약 검사"),
                              ("plan", "실행 없이 실험 조합 확인"),
                              ("run", "준비된 실험 실행 및 보고서 작성")):
        item = sub.add_parser(name, help=description)
        item.add_argument("experiment", type=Path, help="experiment.toml 경로")
        if name == "run":
            item.add_argument("--output", type=Path, help="실행 결과 디렉터리 지정")
    report = sub.add_parser("report", help="실행 요약 확인 또는 HTML 재생성")
    report.add_argument("run_dir", type=Path, help="agent-opt run이 출력한 실행 디렉터리")
    report.add_argument("--csv", type=Path, help="trial 지표를 지정한 CSV 경로로 내보내기")
    report.add_argument("--html", action="store_true", help="독립 HTML 보고서 재생성")
    args = parser.parse_args(argv)
    registry = Registry()
    try:
        if args.command != "doctor" or not (args.dataset or args.plan):
            os.environ.update(network_environment())
        if args.command == "plugins":
            registry.load_project(args.project_root.absolute())
            show(registry.describe())
        elif args.command == "datasets":
            root = args.project_root.absolute()
            inventory, _, _ = component_inventory(root)
            if args.dataset_action == "list":
                show([{**factory().describe(), "name": name}
                      for name, factory in sorted(inventory.factories["datasets"].items())])
            else:
                if not args.name:
                    raise ConfigurationError("Choose a dataset name or a local tasks.json")
                result, _, _ = prepare_selection(root, args.name, evaluator=args.evaluator,
                                                  offline=args.offline)
                show(result)
        elif args.command == "init":
            if not args.dataset:
                raise ConfigurationError("Select a dataset explicitly with --dataset")
            if not args.agent or not (args.argv or args.command_json) or not args.editable:
                raise ConfigurationError("--agent, --argv (or --command-json), and --editable are required")
            if args.argv and args.command_json:
                raise ConfigurationError("Choose either --argv or --command-json")
            command = json.loads(args.command_json) if args.command_json else args.argv
            if not isinstance(command, list) or not command or not all(
                    isinstance(part, str) and part for part in command):
                raise ConfigurationError("Agent argv must be a nonempty JSON string array")
            if not args.yes:
                raise ConfigurationError("Inspect the choices then pass --yes to confirm preparation")
            root = args.project_root.absolute()
            agent = args.agent if args.revision else Path(args.agent)
            if isinstance(agent, Path) and not agent.is_absolute():
                agent = (root / agent).resolve()
            if args.revision and not args.revision.strip():
                raise ConfigurationError("A pinned Git Agent requires a revision")
            name = args.name or (agent.name if isinstance(agent, Path) and agent.is_dir() else "agent")
            name = name.lower().replace(" ", "-")
            inventory, _, _ = component_inventory(root)
            chosen = args.optimizer or ["gepa"]
            custom_configs = json.loads(args.optimizer_config) if args.optimizer_config else {}
            if (not isinstance(custom_configs, dict)
                    or not all(isinstance(name, str) and isinstance(options, dict)
                               for name, options in custom_configs.items())):
                raise ConfigurationError("--optimizer-config must be a JSON mapping of optimizer names to options")
            for optimizer in chosen:
                inventory.resolve("optimizers", optimizer)
            inventory.resolve("harnesses", args.harness)
            target = (choose_editable_file(agent, args.editable, explicit=args.target_file)
                      if "gepa" in chosen else None)
            scaffold = (choose_editable_file(agent, args.editable, suffix=".py",
                                             explicit=args.scaffold_file)
                        if any(o in {"meta_harness", "ecdysis"} for o in chosen) else None)
            if args.revision:
                harness = {"adapter": args.harness, "command": command,
                           "revision": args.revision}
            else:
                harness = {"adapter": args.harness, "command": command}
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
                raise ConfigurationError("TUI requires a TTY for both input and output")
            try:
                init_args = wizard_arguments(args.project_root.absolute())
            except EOFError:
                print(style("TUI cancelled:", "warning", stream=sys.stderr) + " input ended", file=sys.stderr)
                return 2
            except KeyboardInterrupt:
                print("\n" + style("TUI interrupted", "warning", stream=sys.stderr), file=sys.stderr)
                return 130
            print("\n  " + style("Preparing the selected dataset…", "warning", stream=sys.stderr),
                  file=sys.stderr, flush=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(init_args)
            if code:
                return code
            prepared = json.loads(output.getvalue())
            if "session" in prepared:
                return main(["run-session", prepared["session"]])
            experiment = Path(prepared["experiment"])
            spec = load_experiment(experiment)
            with ProgressDisplay() as progress:
                progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                root, summary = run_experiment(spec, Registry(), on_event=progress)
            show({"run_dir": root, "status": summary["status"], "trials_used": summary["trials_used"],
                  "report_html": root / "report.html"})
            return 0 if summary["status"] == "completed" else 3
        elif args.command == "run-session":
            data = json.loads(args.session.read_text(encoding="utf-8"))
            if (data.get("schema_version") != 1 or not isinstance(data.get("experiments"), list)
                    or len(data["experiments"]) < 2):
                raise ConfigurationError("run-session requires at least two prepared experiments")
            base = args.output or args.session.parent.parents[1] / "sessions"
            import time
            import uuid
            session_root = base / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                                   + "-" + uuid.uuid4().hex[:8])
            session_root.mkdir(parents=True, exist_ok=False)
            entries = []
            with ProgressDisplay() as progress:
                for item in data["experiments"]:
                    previous = set((session_root / "runs").iterdir()) if (session_root / "runs").exists() else set()
                    try:
                        spec = load_experiment(Path(item["experiment"]))
                        progress.configure_budget(spec.get("budget", {}).get("max_trials", 100))
                        run, result = run_experiment(spec, Registry(), session_root / "runs",
                                                     on_event=progress)
                        entries.append({"dataset": item["dataset"], "status": result["status"],
                                        "report": "runs/" + run.name + "/report.html",
                                        "trials_used": result["trials_used"]})
                    except (ConfigurationError, UnavailableError, OSError, ValueError) as exc:
                        current = set((session_root / "runs").iterdir()) if (session_root / "runs").exists() else set()
                        new_runs = current - previous
                        candidate = next(iter(new_runs)) if len(new_runs) == 1 else None
                        report = ("runs/" + candidate.name + "/report.html" if candidate is not None
                                  and (candidate / "report.html").is_file() else None)
                        entries.append({"dataset": item["dataset"], "status": "error",
                                        "error": str(exc), "report": report})
            from agent_optimizer.html_report import write_session_index
            index = write_session_index(session_root, entries)
            status = "completed" if all(e["status"] == "completed" for e in entries) else "partial"
            write_json(session_root / "summary.json", {"status": status, "experiments": entries})
            show({"session_dir": session_root, "status": status, "index_html": index,
                  "reports": [session_root / e["report"] for e in entries if e["report"]]})
            return 0 if status == "completed" else 3
        elif args.command == "doctor":
            if args.model and not args.plan:
                raise ConfigurationError("--model requires --plan")
            if args.dataset or args.plan:
                report = (collect_dataset(args.project_root, args.dataset, registry) if args.dataset else
                          collect_plan(args.plan, registry, model=args.model))
                if args.json:
                    show(report)
                else:
                    status = "ready" if report["ready"] else "not ready"
                    print(f"{report['scope']} readiness: "
                          + style(status, "success" if report["ready"] else "error"))
                    for row in report["checks"]:
                        tone = {"ok": "success", "error": "error", "blocked": "warning"}.get(
                            row["status"], "warning")
                        print(f"[{style(row['status'], tone)}] {row['id']}: {row['message']}")
                        if row["remedy"]:
                            print(f"  {style('Remedy:', 'warning')} {row['remedy']}")
                return 0 if report["ready"] else 2
            show(doctor())
        elif args.command == "agents":
            show([load_agent(p) for p in sorted(args.root.rglob("agent.toml"))])
        elif args.command in {"validate", "plan", "run"}:
            spec = load_experiment(args.experiment.resolve())
            if args.command == "run":
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
                from agent_optimizer.html_report import write_html_report
                target = write_html_report(args.run_dir, data)
                show({"html": target, "status": data["status"]})
                return 0
            if args.csv:
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
        print(f"{style('error:', 'error', stream=sys.stderr)} {exc}", file=sys.stderr)
        return 2
    return 0
