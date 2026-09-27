"""Run the installed wheel outside its source tree with a user-owned fixture."""

import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
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
        os.close(slave)
        slave = -1
        os.write(master, f"3\n{declined}\nn\n".encode())
        chunks = []
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
        check_tui_menu(cli, project, environment)
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
        print("wheel-only catalog, TUI, custom init/doctor/run/report: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
