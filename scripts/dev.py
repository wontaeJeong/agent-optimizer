"""개발 명령: setup → doctor → demo. 어느 작업 디렉터리에서나 실행할 수 있습니다."""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Direct Python invocation must be read-only before any project imports/loaders.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.results import write_json
from agent_optimizer.network import network_environment, ca_fingerprint, demo_environment
from agent_optimizer.registry import Registry
from agent_optimizer import readiness
from agent_optimizer.terminal_report import PreparationStatus
from agent_optimizer.terminal_style import ColorArgumentParser, style


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_core(command):
    """Use the project venv, never uv run's implicit environment installation."""
    python = ROOT / ".venv/bin/python"  # Do not resolve executable symlinks.
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONHOME", "PYTHONPATH"}}
    probe = subprocess.run(
        [str(python), "-I", "-B", "-c",
         "import sys; from pathlib import Path; assert sys.version_info >= (3, 11); "
         "assert sys.prefix != sys.base_prefix; "
         "assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()", str(ROOT / ".venv")],
        cwd=ROOT, env=environment, capture_output=True, timeout=15, shell=False,
    )
    if probe.returncode:
        raise UnavailableError("Project .venv is unavailable/incompatible; run sh scripts/bootstrap.sh setup --core")
    commands = {
        "test": ["unittest", "discover", "-s", "tests", "-v"],
        "lint": ["ruff", "check", "."],
        "demo": ["agent_optimizer", "run", "examples/minimal/experiment.toml"],
    }
    code = subprocess.run([str(python), "-m", *commands[command]], cwd=ROOT,
                          env=environment, shell=False).returncode
    if code:
        print(style(f"{command} failed (exit {code})", "error") + "; inspect the command output above. "
              "If dependencies are missing, run sh scripts/bootstrap.sh setup --core.", flush=True)
    return code


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = ColorArgumentParser(description=__doc__, epilog=(
        "코어 사전 준비: Git. ACE 전체 준비에는 Docker Engine/Compose도 필요합니다. "
        "Python이나 make가 없다면 sh scripts/bootstrap.sh setup --core를 사용하세요. "
        "make <명령> ARGS='...'에는 일반 셸 인수를 전달합니다."
    ))
    commands = parser.add_subparsers(dest="command")
    descriptions = {
        "setup": "--core/--dataset 없이: ACE 전체 준비; --core: 코어와 합성 fixture; "
                 "--dataset ID: 선택한 데이터셋 준비",
        "doctor": "--core/--dataset 없이: ACE 전체 진단; --core: 코어 진단; "
                  "--dataset ID: 선택한 데이터셋 읽기 전용 진단; --model: ACE 전체 전용",
        "test": "프로젝트 .venv에서 unittest 실행(Docker 불필요)",
        "lint": "프로젝트 .venv에서 Ruff 검사 실행",
        "demo": "Docker/API 없이 최소 합성 데모 실행",
        "smoke": "실제 RTL/CVDP 평가기 검사 실행",
        "live": "설정한 모델로 반복 최적화 실행(인증 필요)",
        "menu": "대화형 번호 메뉴 열기(TTY 필요, 모델 설정은 세션에서만 유지)",
        "help": "도구 조회나 설치 없이 이 도움말 표시",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description, description=description, allow_abbrev=False)
        if name in {"setup", "doctor"}:
            command.add_argument("--core", action="store_true", help="코어 도구만 준비·진단; Docker/ACE 제외(--dataset/--platform/--model과 함께 사용 불가)")
            command.add_argument("--dataset", metavar="ID", help=(
                "등록 데이터셋 하나 준비(--core/--platform/--model과 함께 사용 불가)" if name == "setup"
                else "등록 데이터셋 하나 진단, 읽기 전용(--core/--platform/--model과 함께 사용 불가)"))
        if name in {"setup", "doctor", "smoke", "live"}:
            command.add_argument("--platform",
                                 help="기본값: Docker daemon의 기본 플랫폼")
        if name == "setup":
            command.add_argument("--offline", action="store_true", help="검증된 캐시 자산만 재사용; 다운로드·빌드 없음")
        if name == "doctor":
            command.add_argument("--json", action="store_true", help="단일 JSON 진단 결과 출력")
            command.add_argument("--model", action="store_true", help="호스트 API와 컨테이너 OpenCode 도구를 명시적으로 호출")
        if name == "live":
            command.add_argument("--iterations", type=int, help="최적화 반복 횟수 지정(1..20, 기본값 3)")
    args = parser.parse_args(argv)
    if args.command in {None, "help"}:
        parser.print_help()
        return 0
    if args.command == "menu":
        return load("dev_menu", "scripts/menu.py").main([])
    if args.command == "live" and args.iterations is not None and not 1 <= args.iterations <= 20:
        parser.error("--iterations must be from 1 to 20")
    core_only = getattr(args, "core", False)
    dataset_id = getattr(args, "dataset", None)
    if dataset_id is not None and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", dataset_id):
        parser.error("--dataset requires an identifier (lowercase letters, digits, _, . or -)")
    if core_only and dataset_id is not None:
        parser.error("--core cannot be combined with --dataset")
    if dataset_id is not None and (args.platform is not None or getattr(args, "model", False)):
        parser.error("--dataset cannot be combined with --platform or --model")
    if core_only and (args.platform is not None or getattr(args, "model", False)):
        parser.error("--core cannot be combined with --platform or --model; omit --core for full ACE commands")
    setup_command = "sh scripts/bootstrap.sh setup"
    if core_only or args.command in {"test", "lint", "demo"}:
        setup_command += " --core"
    elif dataset_id is not None:
        setup_command += f" --dataset {dataset_id}"
    repair = f"Inspect external/setup-logs/ and rerun {setup_command}"
    stage = args.command
    try:
        if args.command == "doctor":
            doctor = load("dev_doctor", Path(__file__).resolve().with_name("dev_doctor.py"))
            with PreparationStatus("environment", action="doctor", subject="check"):
                if dataset_id is not None:
                    report = doctor.collect_report(ROOT, dataset=dataset_id)
                else:
                    report = doctor.collect_report(ROOT, args.platform, core_only=True) if core_only else doctor.collect_report(ROOT, args.platform)
            if args.model:
                checks = load("ace_model_checks", "examples/ace-rtl/environment/model_checks.py")
                checks.check_models(ROOT, report)
            doctor.render_report(report, json_output=args.json)
            return 0 if report["ready"] else 2
        local_bin = str(ROOT / ".cache/uv/bin")
        if local_bin not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
        if args.command in {"setup", "smoke", "live"}:
            os.environ.update(demo_environment())
        os.environ.update(network_environment())
        if args.command in {"test", "lint", "demo"}:
            return run_core(args.command)
        if args.command == "setup" and os.environ.get("AGENT_OPT_BOOTSTRAPPED") != str(ROOT):
            return subprocess.run(["sh", str(ROOT / "scripts/bootstrap.sh"), *argv],
                                  cwd=ROOT, shell=False).returncode
        os.chdir(ROOT)
        if args.command == "setup" and dataset_id is not None:
            stage = "dataset registration"
            registry = Registry()
            registry.load_project(ROOT)
            if dataset_id not in registry.factories["datasets"]:
                raise ConfigurationError(f"Unknown dataset ID: {dataset_id}; run agent-opt datasets list "
                                         "or register it in src/agent_optimizer/registry.py")
            provider = registry.resolve("datasets", dataset_id)()
            stage = "dataset preparation"
            with PreparationStatus(dataset_id, action="setup", subject="dataset"):
                prepared = provider.prepare(ROOT / "external/datasets" / dataset_id, offline=args.offline)
                evaluator_id = prepared.get("evaluator")
                if not isinstance(evaluator_id, str) or ":" in evaluator_id:
                    raise ConfigurationError("Registered dataset provider must return a registered evaluator ID")
                try:
                    registry.resolve("evaluators", evaluator_id)
                except UnavailableError:
                    raise ConfigurationError(f"Dataset provider returned unregistered evaluator ID {evaluator_id!r}; "
                                             "register it in src/agent_optimizer/registry.py") from None
            stage = "final doctor"
            doctor = load("dev_doctor", Path(__file__).resolve().with_name("dev_doctor.py"))
            with PreparationStatus("dataset", action="doctor", subject="check"):
                report = doctor.collect_report(ROOT, dataset=dataset_id)
                if not report["ready"]:
                    raise UnavailableError("Selected dataset doctor failed; follow the diagnostic repair instructions")
            doctor.render_report(report)
            print(json.dumps({"status": "ready", "scope": "dataset", "dataset": dataset_id,
                              "next": f'make doctor ARGS="--dataset {dataset_id} --json"'}))
            return 0
        if not core_only:
            setup = load("ace_environment", "examples/ace-rtl/environment/setup.py")
            if args.command == "live":
                setup.validate_live()  # Before image probes, data reads, or any model execution.
            args.platform = setup.validate_platform(args.platform)
        if args.command == "setup":
            if not core_only:
                stage = "example environment"
                print(style(f"[setup] {stage}: starting", "warning")
                      + f"; logs: {ROOT / 'external/setup-logs'}", flush=True)
                dataset, lock = setup.prepare_environment(offline=args.offline, platform=args.platform)
                print(style(f"[setup] {stage}: complete", "success"), flush=True)
                stage = "dataset preparation"
                print(style(f"[setup] {stage}: starting", "warning")
                      + f"; output: {ROOT / 'datasets/ace-demo'}", flush=True)
                prepare = load("ace_prepare", "examples/ace-rtl/prepare.py")
                manifest = prepare.prepare_dataset(dataset, ROOT / "datasets/ace-demo/all-tasks.json", lock)
                demo = load("ace_demo", "examples/ace-rtl/environment/demo.py")
                manifest = demo.select_tasks(manifest)
                write_json(ROOT / "datasets/ace-demo/tasks.json", manifest)
                print(style(f"[setup] {stage}: complete", "success"), flush=True)
            stage = "final doctor"
            print(style(f"[setup] {stage}: starting", "warning") + " (read-only)", flush=True)
            doctor = load("dev_doctor", Path(__file__).resolve().with_name("dev_doctor.py"))
            report = doctor.collect_report(ROOT, args.platform, core_only=True) if core_only else doctor.collect_report(ROOT, args.platform)
            doctor.render_report(report)
            if not report["ready"]:
                raise UnavailableError("Final doctor failed; follow the diagnostic repair instructions")
            print(style(f"[setup] {stage}: complete", "success"), flush=True)
            stage = "minimal demo"
            print(style(f"[setup] {stage}: starting", "warning")
                  + f"; results: {ROOT / 'runs'}", flush=True)
            code = run_core("demo")
            if code:
                raise UnavailableError(f"Minimal demo failed (exit {code}); inspect runs/")
            print(style(f"[setup] {stage}: complete", "success"), flush=True)
            if core_only:
                print(json.dumps({"status": "ready", "scope": "core", "results": "runs/",
                                  "next": 'make doctor ARGS="--core"; make menu; make demo'}))
            else:
                print(json.dumps({"status": "ready", "environment_lock": "external/environment-lock.json",
                                  "results": "runs/", "next": "make doctor; make test; make smoke"}))
            return 0
        lock_path = ROOT / "external/environment-lock.json"
        if not lock_path.is_file():
            raise UnavailableError("blocked_environment: run python scripts/dev.py setup first")
        lock = setup.read_environment_lock(lock_path)
        if lock["platform"] != args.platform:
            raise ConfigurationError("Prepared platform differs; use matching --platform")
        if lock.get("ca_bundle_sha256") != ca_fingerprint():
            raise ConfigurationError("CA bundle differs from prepared images; rerun setup")
        with PreparationStatus("environment", action=args.command, subject="check"):
            setup.prepare_sources(ROOT / "external", offline=True)
            setup.prepare_data(ROOT / "external", offline=True)
            setup.validate_driver_lock(ROOT / "external", lock)
            sim_image = setup.verified_sim_image(lock)
            capability = setup.doctor(ROOT / "external", args.platform,
                                      lock["images"]["evaluation"]["id"], lock["images"]["agent"]["id"])
            write_json(ROOT / "external/setup-logs/doctor.json", capability)
            if not capability["ready"]:
                raise UnavailableError("blocked_environment: execution doctor failed; inspect external/setup-logs/doctor.json")
        os.environ["DOCKER_DEFAULT_PLATFORM"] = args.platform
        os.environ["OSS_SIM_IMAGE"] = sim_image
        example = load("ace_dev_checks", "examples/ace-rtl/environment/checks.py")
        if args.command == "smoke":
            return example.smoke(lock)
        return example.live(lock, iterations=args.iterations) if args.iterations is not None else example.live(lock)
    except (ConfigurationError, UnavailableError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "stage": stage, "reason": str(exc),
                          "repair": repair}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "stage": stage,
                          "repair": repair}))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
