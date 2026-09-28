"""Run the installed wheel outside its source tree with a user-owned fixture."""

import json
import os
import pty
import select
import shutil
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


def check_tui_menu(cli: Path, project: Path, environment: dict) -> None:
    declined = project / "declined ace"
    master, slave = pty.openpty()
    try:
        child = subprocess.Popen([str(cli), "tui", "--project-root", str(project)],
                                  cwd=project, env=environment, stdin=slave, stderr=slave,
                                  stdout=subprocess.PIPE, text=True)
        chunks = []
        while "Agent Optimizer · Agent".encode() not in b"".join(chunks):
            if not select.select([master], [], [], 30)[0]:
                raise AssertionError("설치형 TUI 프리셋 시작 화면을 기다리다 제한 시간을 넘겼습니다")
            chunks.append(os.read(master, 4096))
        deadline = time.monotonic() + 5
        while termios.tcgetattr(slave)[3] & termios.ICANON:
            if time.monotonic() > deadline:
                raise AssertionError("설치형 TUI가 키 입력을 준비하지 않았습니다")
            time.sleep(0.005)
        os.write(master, b"\x1b")
        while "선택 [5/1/2/3/4]".encode() not in b"".join(chunks):
            if not select.select([master], [], [], 30)[0]:
                raise AssertionError("설치형 TUI 이전 메뉴를 기다리다 제한 시간을 넘겼습니다")
            chunks.append(os.read(master, 4096))
        os.write(master, f"3\n{declined}\nn\n".encode())
        os.close(slave)
        slave = -1
        while True:
            readable, _, _ = select.select([master], [], [], 30)
            if not readable:
                raise AssertionError("설치형 TUI 선택 입력을 기다리다 제한 시간을 넘겼습니다")
            try:
                part = os.read(master, 4096)
            except OSError:
                break
            if not part:
                break
            chunks.append(part)
        stdout, _ = child.communicate(timeout=30)
        transcript = b"".join(chunks).decode(errors="replace")
        if (child.returncode != 2 or "3. ACE-RTL + CVDP 예제" not in transcript
                or str(declined) not in transcript or stdout or declined.exists()):
            raise AssertionError(f"설치형 TUI rc={child.returncode}, stdout={stdout!r}, stderr={transcript!r}")
    finally:
        if slave >= 0:
            os.close(slave)
        os.close(master)


def check_preset_cancel(cli: Path, project: Path, environment: dict) -> None:
    master, slave = pty.openpty()
    workspace = project / "chosen ace"
    try:
        child = subprocess.Popen([str(cli), "tui", "--project-root", str(project)],
                                 cwd=project, env=environment, stdin=slave, stderr=slave,
                                 stdout=subprocess.PIPE, text=True)
        transcript = bytearray()

        def until(text: str) -> None:
            marker = text.encode()
            deadline = time.monotonic() + 15
            while marker not in transcript:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([master], [], [], remaining)[0]:
                    raise AssertionError(f"선택형 설치 TUI 단계 대기 시간 초과: {text}; "
                                         f"화면: {transcript.decode(errors='replace')[-1000:]}")
                transcript.extend(os.read(master, 4096))

        def await_raw() -> None:
            deadline = time.monotonic() + 5
            while termios.tcgetattr(slave)[3] & termios.ICANON:
                if time.monotonic() > deadline:
                    raise AssertionError("선택형 TUI 키 입력 상태가 준비되지 않았습니다: "
                                         f"rc={child.poll()}, 화면={transcript.decode(errors='replace')[-1200:]}")
                time.sleep(0.005)

        until("Agent Optimizer · Agent")
        await_raw()
        os.write(master, b"\r")
        until("Agent Optimizer · Harness")
        await_raw()
        os.write(master, b"\r")
        until("Agent Optimizer · Optimizer")
        await_raw()
        os.write(master, b"\x1b[B")
        until("> Meta-Harness")
        if "후보별 skills/ace-rtl/scripts/agent_" not in transcript.decode(errors="replace"):
            raise AssertionError("방향키 초점이 Meta-Harness 설명을 갱신하지 않았습니다")
        await_raw()
        os.write(master, b"\r")
        until("Agent Optimizer · Dataset")
        await_raw()
        os.write(master, b"\r")
        until("ACE-RTL 작업공간 경로:")
        os.write(master, (str(workspace) + "\n").encode())
        until("준비하고 실행할까요?")
        os.write(master, b"n\n")
        stdout, _ = child.communicate(timeout=15)
        if child.returncode != 2 or stdout or workspace.exists() or (project / "runs").exists():
            raise AssertionError("wheel-only 선택형 TUI가 취소 전 자산을 생성했습니다")
    finally:
        if slave >= 0:
            os.close(slave)
        os.close(master)


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
