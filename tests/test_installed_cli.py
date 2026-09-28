"""Run the installed wheel outside its source tree with a user-owned fixture."""

import json
import fcntl
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def invoke(cli: Path, project: Path, environment: dict, *args: str) -> dict:
    result = subprocess.run([str(cli), *args], cwd=project, env=environment,
                            capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        raise AssertionError(f"{args}: exit={result.returncode}; stderr={result.stderr}")
    return json.loads(result.stdout)


def interact_tui(cli: Path, project: Path, environment: dict,
                 actions: list[tuple[str, bytes]], size: tuple[int, int] = (30, 100)) -> str:
    """Drive the installed Textual app through a real, continuously drained PTY."""
    master, slave = pty.openpty()
    child = None
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", size[0], size[1], 0, 0))
        child = subprocess.Popen([str(cli), "tui", "--project-root", str(project)],
                                  cwd=project, env={**environment, "AGENT_OPT_LANG": "ko"},
                                  stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        transcript = bytearray()
        cursor = 0
        last_marker = "startup"

        def visible() -> str:
            return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "",
                          transcript[cursor:].decode(errors="replace"))

        for marker, keys in actions:
            last_marker = marker
            deadline = time.monotonic() + 12
            while marker not in visible():
                if time.monotonic() > deadline or child.poll() is not None:
                    raise AssertionError(f"설치형 Textual TUI 화면 대기: {marker}; "
                                         f"rc={child.poll()}, 화면={visible()[-1200:]}")
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        transcript.extend(os.read(master, 65536))
                    except OSError as exc:
                        raise AssertionError(f"설치형 TUI PTY 읽기 실패: {exc}") from exc
            cursor = len(transcript)
            os.write(master, keys)
        deadline = time.monotonic() + 12
        while child.poll() is None:
            if time.monotonic() > deadline:
                raise AssertionError(f"설치형 Textual TUI 종료 시간 초과 after {last_marker}: "
                                     f"{visible()[-1200:]}")
            if select.select([master], [], [], 0.1)[0]:
                try:
                    transcript.extend(os.read(master, 65536))
                except OSError:
                    break
        if child.wait(timeout=2) != 0:
            raise AssertionError(f"설치형 Textual TUI 종료 코드 {child.returncode}: {visible()[-1200:]}")
        return transcript.decode(errors="replace")
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        os.close(slave)
        os.close(master)


def check_tui_menu(cli: Path, project: Path, environment: dict) -> None:
    master, slave = pty.openpty()
    try:
        result = subprocess.run([str(cli), "tui", "--project-root", str(project)],
                                cwd=project, env=environment, stdin=slave, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10)
        if result.returncode != 2 or b"TTY" not in result.stderr:
            raise AssertionError("설치형 Textual TUI가 파이프 출력을 거부하지 않았습니다")
    finally:
        os.close(slave)
        os.close(master)
    interact_tui(cli, project, environment, [
        ("새 최적화", b"\r"),
        ("ACE-RTL", b"\x1b"),
        ("실행할 작업을 선택하세요", b"\x1b[B\x1b[B\r"),
        ("표시할 항목이 없습니다", b"\x1b"),
        ("실행할 작업을 선택하세요", b"q"),
    ])
    if (project / "runs").exists():
        raise AssertionError("이력 조회가 사용자 프로젝트에 파일을 작성했습니다")


def check_preset_cancel(cli: Path, project: Path, environment: dict) -> None:
    workspace = project / "chosen ace"
    interact_tui(cli, project, environment, [
        ("새 최적화", b"\r"),
        ("ACE-RTL", b"\r"),
        ("OpenCode", b"\r"),
        ("GEPA", b"\x1b[B\r"),
        ("CVDP", b"\r"),
        ("ACE 작업공간", (str(workspace) + "\r").encode()),
        ("모델 설정", b"\x1b"),
        ("ACE 작업공간", b"\x1b"),
        ("Dataset", b"q"),
    ])
    if workspace.exists() or (project / "runs").exists():
        raise AssertionError("wheel-only Textual TUI가 실행 취소 전에 자산을 생성했습니다")


def check_tui_existing_run(cli: Path, project: Path, environment: dict,
                           experiment: Path, check_count: int) -> None:
    evaluator = project / "evaluator.py"
    source = evaluator.read_text(encoding="utf-8")
    needle = "        spec = task.evaluation\n"
    if needle not in source:
        raise AssertionError("PTY fixture evaluator no longer has its expected method boundary")
    evaluator.write_text(source.replace(needle, "        import time\n        time.sleep(0.2)\n" + needle),
                         encoding="utf-8")
    before = len(list((project / "runs").glob("*/report.html")))
    transcript = interact_tui(cli, project, environment, [
        ("실행할 작업을 선택하세요", b"\x1b[B\r"),
        ("기존 experiment.toml 경로", (str(experiment) + "\r").encode()),
        ("실행 전 확인", b"\x1b[B\r"),
        ("준비 중", b""),
        ("Doctor로 계속", b"\r"),
        ("plan.schema", b"\x1b[B" * check_count + b"\r"),
        ("실행 중", b""),
        ("최적화 완료", b"q"),
    ], size=(20, 50))
    for marker in ("Trial budget", "평가 완료", "최적화 완료"):
        if marker not in transcript:
            raise AssertionError(f"설치형 TUI에서 {marker} PTY 근거를 찾지 못했습니다")
    after = len(list((project / "runs").glob("*/report.html")))
    if after != before + 1:
        raise AssertionError(f"설치형 TUI 실행 보고서 수가 증가하지 않았습니다: {before} → {after}")


def main(wheel: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="installed agent opt ") as directory:
        outside = Path(directory)
        virtualenv = outside / "venv"
        project = outside / "user workspace"
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"PYTHONPATH", "PYTHONHOME"} and not key.startswith("AGENT_OPT_MODEL_")}
        uv = shutil.which("uv")
        if uv:
            subprocess.run([uv, "venv", "--seed", "--python", sys.executable, str(virtualenv)],
                           check=True, env=environment, capture_output=True, text=True, timeout=120)
        else:
            venv.EnvBuilder(with_pip=True).create(virtualenv)
        project.mkdir()
        python = virtualenv / "bin/python"
        cli = virtualenv / "bin/agent-opt"
        installed = subprocess.run([str(python), "-m", "pip", "install", str(wheel.resolve())],
                                   check=True, cwd=outside, env=environment,
                                   capture_output=True, text=True, timeout=180)
        if not cli.is_file():
            raise AssertionError(f"설치된 명령이 없습니다: {[p.name for p in (virtualenv / 'bin').iterdir()]}; "
                                 f"pip={installed.stdout} {installed.stderr}")

        source = ROOT / "examples/minimal"
        agent = project / "agents/solo"
        shutil.copytree(source / "agents/solo", agent)
        shutil.copyfile(source / "tasks.json", project / "tasks.json")
        shutil.copyfile(source / "evaluator.py", project / "evaluator.py")
        before = (agent / "configs/strategy.json").read_bytes()

        for argv in ([str(python), "-I", "-m", "agent_optimizer", "--help"],
                     [str(cli), "--help"]):
            subprocess.run(argv, cwd=project, env=environment, capture_output=True,
                           text=True, check=True, timeout=30)
        try:
            catalog = invoke(cli, project, environment, "datasets", "list")
        except FileNotFoundError as exc:
            raise AssertionError(f"설치형 CLI를 실행할 수 없습니다: {cli.read_text().splitlines()[0]}") from exc
        if {row["name"] for row in catalog} != {"cvdp", "verilog-spec", "verilog-completion"}:
            raise AssertionError(f"독립 설치 데이터셋 카탈로그 오류: {catalog}")
        for kind, name in (("agent", "ace-rtl"), ("harness", "ace-opencode"),
                           ("optimizer", "gepa"), ("optimizer", "meta_harness"),
                           ("dataset", "cvdp")):
            choices = invoke(cli, project, environment, "catalog", "list", "--kind", kind, "--json")
            if name not in {row["id"] for row in choices}:
                raise AssertionError(f"설치형 catalog {kind}/{name} 누락: {choices}")
        unprepared = invoke(cli, project, environment, "catalog", "show", "agent", "ace-rtl", "--json")
        if unprepared["ready"] or not unprepared["implemented"]:
            raise AssertionError(f"미준비 ACE 상태를 성공으로 표현했습니다: {unprepared}")
        invalid = subprocess.run([str(cli), "init", "--name", "invalid-ace",
                                  "--agent-preset", "ace-rtl", "--harness-profile", "codex",
                                  "--optimizer", "gepa", "--dataset", "cvdp", "--yes"],
                                 cwd=project, env=environment, capture_output=True,
                                 text=True, timeout=30)
        if (invalid.returncode != 2 or invalid.stdout or (project / "external").exists()
                or (project / "runs/configs/invalid-ace").exists()):
            raise AssertionError(f"설치형 미구현 조합이 준비 전에 차단되지 않았습니다: {invalid}")
        check_tui_menu(cli, project, environment)
        check_preset_cancel(cli, project, environment)
        prepared = invoke(cli, project, environment, "init", "--name", "wheel-fixture",
                          "--agent", "agents/solo", "--command",
                          "{python} {agent_dir}/src/fixture_agent.py {task_dir}",
                          "--editable", "configs/strategy.json", "--dataset", "tasks.json",
                          "--evaluator", "evaluator.py:TextFixtureEvaluator",
                          "--optimizer", "baseline", "--yes")
        experiment = Path(prepared["experiment"])
        readiness = invoke(cli, project, environment, "doctor", "--plan", str(experiment), "--json")
        if not readiness["ready"]:
            raise AssertionError(f"독립 설치 계획 진단 실패: {readiness}")
        if list(project.rglob("__pycache__")):
            raise AssertionError("설치형 doctor가 사용자 파일에 bytecode를 기록했습니다")
        result = invoke(cli, project, environment, "run", str(experiment))
        run_dir = Path(result["run_dir"])
        if result["status"] != "completed" or not (run_dir / "report.html").is_file():
            raise AssertionError(f"독립 설치 실행 보고서 실패: {result}")
        summary = invoke(cli, project, environment, "report", str(run_dir))
        if summary["status"] != "completed" or (agent / "configs/strategy.json").read_bytes() != before:
            raise AssertionError("독립 설치 실행이 원본을 수정했거나 결과를 잃었습니다")
        check_tui_existing_run(cli, project, environment, experiment, len(readiness["checks"]))
        # Installed package contract only: substitute the external ACE preparation
        # while retaining the real wheel CLI, configuration loader, and pinned templates.
        shutil.copytree(ROOT / "examples/ace-rtl", project / "examples/ace-rtl",
                        ignore=shutil.ignore_patterns("__pycache__"))
        ace_tasks = json.loads((source / "tasks.json").read_text())
        ace_tasks["tasks"] = ace_tasks["tasks"][:2]
        ace_data = project / "datasets/ace-demo/tasks.json"
        ace_data.parent.mkdir(parents=True)
        ace_data.write_text(json.dumps(ace_tasks))
        script = '''import contextlib, io, json
from pathlib import Path
from unittest.mock import patch
from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.preset_tui import verify_ace_selection
for optimizer in ("gepa", "meta_harness"):
    output = io.StringIO()
    with patch("agent_optimizer.preset_tui.prepare_ace_selection"), contextlib.redirect_stdout(output):
        code = main(["init", "--name", "installed-" + optimizer, "--agent-preset", "ace-rtl",
                     "--harness-profile", "ace-opencode", "--optimizer", optimizer,
                     "--dataset", "cvdp", "--yes"])
    assert code == 0, code
    path = Path(json.loads(output.getvalue())["experiment"])
    spec = load_experiment(path)
    verify_ace_selection(spec)
    assert spec["stages"][0]["optimizer"] == optimizer
    with patch("agent_optimizer.preset_tui.prepare_ace_selection"), contextlib.redirect_stdout(io.StringIO()) as prepared:
        assert main(["prepare", str(path), "--offline"]) == 0
    assert json.loads(prepared.getvalue())["experiment"] == str(path)
print("설치형 GEPA/Meta 설정 생성·고정 계약: 외부 자산 준비 모의 확인")'''
        preset = subprocess.run([str(python), "-I", "-c", script], cwd=project,
                                env=environment, capture_output=True, text=True, timeout=30)
        if preset.returncode or "외부 자산 준비 모의 확인" not in preset.stdout:
            raise AssertionError(f"설치형 프리셋 계약 실패: {preset.stdout} {preset.stderr}")
        print("설치형 catalog/TUI/사용자 설정 실행 통과; ACE GEPA/Meta 생성·prepare는 외부 준비 모의 계약 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
