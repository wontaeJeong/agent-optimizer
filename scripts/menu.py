"""대화형 번호 메뉴. 자동화에는 명시적 명령을 사용합니다."""
import getpass
import os
import stat
import subprocess
import sys
import warnings
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.models import ModelSettings
from agent_optimizer.korean_help import KoreanArgumentParser

MENU = """
1. 코어 개발 환경 설치
2. 코어 환경 진단
3. LLM 없이 데모·최적화 반복 테스트
4. 모델 설정·연결 검사
5. ACE 최적화 실행 — 반복 횟수 선택
6. 실행 결과·보고서 확인
7. ACE 전체 환경 준비 — Docker·평가/모델 실행 자산
8. 일반 Agent 최적화 TUI
0. 종료"""


def execute(argv, env, *, return_code=False):
    result = subprocess.run(argv, cwd=ROOT, env=env.copy(), shell=False)
    if result.returncode:
        print(f"명령 실패 (exit {result.returncode}). 위 출력을 확인하세요; 자동 재시도하지 않습니다.")
    return result.returncode if return_code else result.returncode == 0


def bootstrap(command, env, *args):
    return execute(["sh", str(ROOT / "scripts/bootstrap.sh"), command, *args], env)


def agent_tui(env):
    cli = ROOT / ".venv/bin/agent-opt"
    if not cli.is_file():
        print("프로젝트 .venv가 필요합니다: sh scripts/bootstrap.sh setup --core")
        return 2
    return execute([str(cli), "tui"], env, return_code=True)


def local_demo(env):
    python = ROOT / ".venv/bin/python"  # Preserve virtualenv executable identity.
    if not python.is_file():
        print("프로젝트 .venv가 필요합니다: sh scripts/bootstrap.sh setup --core")
        return
    print("합성 최소 데모 후 로컬 HTTP fixture 기반 Optimizer 회귀 테스트 (외부 LLM·Docker 없음).")
    if bootstrap("demo", env):
        test_env = {key: value for key, value in env.items() if key not in {"PYTHONHOME", "PYTHONPATH"}}
        execute([str(python), "-m", "unittest", "discover", "-s", "tests",
                 "-p", "test_feedback_optimizer.py", "-v"], test_env)


def configure_model(env):
    print("Docker·ACE 평가/모델 실행 자산이 필요하면 먼저 7번 ACE 전체 환경 준비를 선택하세요.")
    print("이 작업은 doctor --model로 실제 모델 API·컨테이너 도구를 호출합니다. 설정은 현재 세션에만 유지됩니다.")
    staged = env.copy()
    default = "2" if staged.get("MODEL_BASE_URL") and not staged.get("MODEL_ENDPOINT") else "1"
    mode = input(f"URL 방식: 1=정확한 endpoint, 2=표준 base URL [{default}]: ").strip() or default
    if mode not in {"1", "2"}:
        raise ConfigurationError("URL 방식은 1 또는 2를 선택하세요.")
    name, unused = ("MODEL_ENDPOINT", "MODEL_BASE_URL") if mode == "1" else ("MODEL_BASE_URL", "MODEL_ENDPOINT")
    # Do not redisplay endpoint values (including malformed inherited credentials).
    url = input(f"{name} (빈 입력: 기존 값 유지): ").strip()
    staged[name] = url or staged.get(name, "")
    staged.pop(unused, None)
    model = input("MODEL_ID (빈 입력: 기존 값 또는 glm5.3-flash): ").strip()
    staged["MODEL_ID"] = model or staged.get("MODEL_ID") or "glm5.3-flash"
    # getpass warns before falling back to echoed input: turn that warning into an abort.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        token = getpass.getpass("Bearer token (숨김, 빈 입력: 기존 값 유지): ")
    staged["MODEL_API_KEY"] = token or staged.get("MODEL_API_KEY", "")
    ModelSettings.from_env(staged)
    env.clear()
    env.update(staged)
    bootstrap("doctor", env, "--model")


def live(env):
    print("ACE 실행에는 7번 전체 환경 준비와 4번 모델 설정이 필요합니다.")
    try:
        ModelSettings.from_env(env)
    except (ConfigurationError, UnavailableError, ValueError):
        print("모델 설정이 없거나 잘못되었습니다. 먼저 4번 모델 설정·연결 검사를 선택하세요.")
        return
    text = input("반복 횟수 [3] (1..20): ").strip() or "3"
    if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= 20:
        raise ConfigurationError("반복 횟수는 1..20 정수여야 합니다.")
    print("설정한 모델로 실제 ACE 최적화를 실행합니다.")
    bootstrap("live", env, "--iterations", str(int(text)))


def read_report(relative):
    """Open only report.md beneath real runs directories, including at selection time."""
    if relative.name != "report.md" or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid report path")
    directory = os.open(ROOT / "runs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        file = os.open("report.md", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(file, encoding="utf-8") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Report must be a regular file")
            return stream.read()
    finally:
        os.close(directory)


def reports():
    runs = ROOT / "runs"
    found = []
    if runs.is_dir() and not runs.is_symlink():
        # Existing minimal and dev live output layouts; never recursively scan task outputs.
        for parent in (runs, runs / "dev-live"):
            if parent.is_symlink() or not parent.is_dir():
                continue
            for directory in sorted(parent.iterdir()):
                report = directory / "report.md"
                if directory.is_dir() and not directory.is_symlink() and report.is_file() and not report.is_symlink():
                    found.append(report.relative_to(runs))
    if not found:
        print("보고서가 없습니다. 3번 데모 또는 5번 실행 후 확인하세요.")
        return
    for index, path in enumerate(found, 1):
        print(f"{index}. {path}")
    choice = input("보고서 번호 (0: 돌아가기): ").strip()
    if choice == "0":
        return
    if not choice.isascii() or not choice.isdecimal() or not 1 <= int(choice) <= len(found):
        raise ConfigurationError("목록의 보고서 번호를 선택하세요.")
    print(read_report(found[int(choice) - 1]))


def main(argv=None, *, env=None):
    parser = KoreanArgumentParser(description=__doc__, epilog="TTY 필요. 자동화에는 setup/doctor/demo/live 명령을 사용하세요.")
    parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("menu requires a TTY; 자동화에는 setup/doctor/demo/live 등 명시적 명령을 사용하세요.")
        return 2
    session = dict(os.environ if env is None else env)
    last_tui_code = 0
    try:
        while True:
            print(MENU)
            choice = input("선택: ").strip()
            if choice == "0":
                return last_tui_code
            try:
                if choice in {"1", "2"}:
                    bootstrap("setup" if choice == "1" else "doctor", session, "--core")
                elif choice == "3":
                    local_demo(session)
                elif choice == "4":
                    configure_model(session)
                elif choice == "5":
                    live(session)
                elif choice == "6":
                    reports()
                elif choice == "7":
                    bootstrap("setup", session)
                elif choice == "8":
                    last_tui_code = agent_tui(session)
                else:
                    print("0..8 중 번호를 선택하세요.")
            except (ConfigurationError, UnavailableError) as exc:
                print(f"실행하지 못했습니다: {exc}")
            except getpass.GetPassWarning:
                print("숨김 토큰 입력이 불가능하여 취소했습니다. TTY를 확인하세요.")
            except (OSError, ValueError, subprocess.SubprocessError):
                # Do not echo exception payloads that could contain URLs or credentials.
                print("명령 또는 보고서 처리 실패. 코어는 1번, ACE 평가/모델 실행 자산은 7번 준비 후 다시 확인하세요.")
    except EOFError:
        print("\n종료합니다.")
        return 0
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
