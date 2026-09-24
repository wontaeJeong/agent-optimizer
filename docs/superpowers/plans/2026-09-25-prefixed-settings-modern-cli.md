# 접두어 설정·현대적 CLI 구현 계획

> **구현 담당:** 작업별로 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용합니다. 각 단계는 체크박스(`- [ ]`)로 추적합니다.

**목표:** 프로젝트 환경변수에 `AGENT_OPT_` 접두어를 적용하고 Pydantic Settings·Typer·Rich를 각각 모델 입력·공개 CLI·대화형 진행 표시에 사용합니다.

**구조:** `ModelSettings.from_env(env=None) -> ModelSettings`와 기존 공개 필드를 모델 설정 진입점으로 유지합니다. `agent-opt`의 파싱만 Typer로 옮겨 현재 experiment/registry/doctor 실행 로직에 전달합니다. Rich는 TTY를 표시하고 비TTY stderr 이벤트·JSON stdout은 유지합니다.

**기술:** Python >=3.11, `pydantic-settings`(Pydantic v2), Typer, Rich, uv frozen lock, unittest, Ruff.

**설계:** `docs/superpowers/specs/2026-09-25-prefixed-settings-modern-cli-design.md`

## 공통 제약

- 프로젝트 변수는 `AGENT_OPT_MODEL_ENDPOINT`, `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`, `AGENT_OPT_CVDP_PYTHON`을 사용합니다. 기존 `MODEL_*`/`CVDP_PYTHON` 입력은 즉시 중단합니다.
- `OSS_SIM_IMAGE`·`OPENCODE_CONFIG`·`OPENROUTER_API_KEY`·proxy/TLS·`DOCKER_DEFAULT_PLATFORM`·`UV_*`·`PATH`·`PYTHONPATH`는 외부 이름을 유지합니다.
- `.env`를 자동 로드하거나 인증 값을 진단·repr·실험 산출물에 노출하지 않습니다. 점수와 데이터/소스 pin도 바꾸지 않습니다.
- 설치 전 `scripts/dev.py`/bootstrap은 표준 라이브러리로 동작해야 합니다. doctor 읽기 전용과 JSON stdout을 유지합니다.
- `agent-opt init`은 JSON argv 배열 `--command-json`만 받고 `--argv`는 제거합니다.
- 과거 검증 결과를 현재 명령으로 소급 수정하지 않습니다.

## 파일 책임

- `pyproject.toml`, `uv.lock`: 런타임 의존성과 frozen lock.
- `src/agent_optimizer/models.py`: 모델 설정 입력·검증·키 비노출.
- `src/agent_optimizer/cli.py`: Typer 명령과 기존 실행 분기. 병렬 registry는 추가하지 않습니다.
- `src/agent_optimizer/terminal_report.py`: Rich TTY stderr와 비TTY 일반 로그.
- `src/agent_optimizer/readiness.py`, `scripts/menu.py`, `examples/ace-rtl/environment/{diagnostics.py,setup.py,model_checks.py}`, `examples/ace-rtl/evaluator.py`, `scripts/dev.py`: 환경변수 소비·생성.
- `examples/ace-rtl/harness.toml`, `examples/ace-rtl/environment/openai-compatible.json`, `examples/rtl-debugger/{harness.toml,compatible.json,endpoint-plugin.mjs}`: 컨테이너 전달·provider 설정.
- `.env.example`, `README.md`, `docs/development.md`, `experiments/simple-feedback/README.md`, `examples/{ace-rtl,rtl-debugger}/README.md`, `docs/SOURCES.md`: 현재 사용 안내와 패키지 출처.
- `tests/test_models.py`, `tests/test_cli_experience.py`, `tests/test_progress.py`, `tests/test_menu.py`, `tests/test_dev_environment.py`, `tests/test_demo_environment.py`, `tests/test_network.py` 등: 동작 회귀와 기존 입력명 교체.

### 작업 1: 의존성을 고정하고 모델 입력을 접두어로 전환

**파일:** `pyproject.toml`, `uv.lock`, `src/agent_optimizer/models.py`, `tests/test_models.py` 수정.

**계약:** `ModelSettings.from_env(env=None) -> ModelSettings`, `.endpoint`, `.model`, `.api_key`, worker의 `{"settings": {...}}` 형태 유지. 후속 작업은 새 `AGENT_OPT_MODEL_*` 이름을 사용합니다.

- [ ] **1단계: 실패 테스트.** 모델 테스트의 입력을 `AGENT_OPT_MODEL_ENDPOINT`, `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`로 변경합니다. 명시적 mapping 격리, 옛 이름 거부, 키 비노출을 검사합니다.

```python
def test_prefixed_only_and_explicit_mapping_isolation(self):
    new = {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1/chat/completions",
           "AGENT_OPT_MODEL_API_KEY": "fixture-secret"}
    with patch.dict(os.environ, {"MODEL_ENDPOINT": new["AGENT_OPT_MODEL_ENDPOINT"],
                                 "MODEL_API_KEY": "old-secret"}, clear=True):
        with self.assertRaises((ConfigurationError, UnavailableError)):
            ModelSettings.from_env()
        settings = ModelSettings.from_env(new)
        self.assertEqual(settings.model, "glm5.3-flash")
        self.assertNotIn("fixture-secret", repr(settings))
        with self.assertRaises((ConfigurationError, UnavailableError)):
            ModelSettings.from_env({"MODEL_ENDPOINT": new["AGENT_OPT_MODEL_ENDPOINT"],
                                    "MODEL_API_KEY": "old-secret"})
```

- [ ] **2단계: 실패 확인.** `PYTHONPATH=src python3 -m unittest discover -s tests -p test_models.py -v`에서 새 이름으로 실패하는지 확인합니다.
- [ ] **3단계: 의존성.** `pyproject.toml`의 `dependencies = ["pydantic-settings>=2,<3", "typer>=0.16,<1", "rich>=14,<15"]`; `uv lock`, `uv sync --frozen --python 3.12 --extra dev`를 이 워크트리에서 실행합니다. Python 3.11 호환성을 확인하고 현재 안정판이 범위를 넘었으면 범위를 검토해 재고정합니다.
- [ ] **4단계: 구현.** 설치 전 `registry.py`가 `models.py`를 간접 import하므로 `ModelSettings.from_env`에서만 `pydantic_settings`를 로드합니다. 비공개 `BaseSettings`의 `endpoint`·`base_url`·`id`·`api_key`에 `SettingsConfigDict(env_prefix="AGENT_OPT_MODEL_", env_file=None)`를 적용합니다. 명시 mapping이면 모든 필드를 직접 지정해 프로세스 환경 유입을 막습니다. 기존 URL/공백 검증과 비노출 `ModelSettings`를 유지하고, 의존성·검증 오류에 키를 포함하지 않습니다. `asdict(settings)`는 worker payload에만 사용합니다.
- [ ] **5단계: 통과 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_models.py -v`로 timeout·HTTP·인증 값 비노출을 확인합니다.
- [ ] **6단계: 커밋.** status/diff/log 확인 후 네 파일만 `Use prefixed Pydantic model settings`로 커밋합니다.

### 작업 2: 진단과 예제에 프로젝트 변수명을 전파

**파일:** `src/agent_optimizer/readiness.py`, `scripts/menu.py`, `scripts/dev.py`, `examples/ace-rtl/{evaluator.py,harness.toml,README.md}`, `examples/ace-rtl/environment/{diagnostics.py,setup.py,model_checks.py,openai-compatible.json}`, `examples/rtl-debugger/{harness.toml,compatible.json,endpoint-plugin.mjs,README.md}`, `tests/test_menu.py`, `tests/test_dev_environment.py`, `tests/test_demo_environment.py`, `tests/test_network.py`, `tests/test_cli_experience.py` 및 전체 검색으로 찾은 소비자·fixture.

**계약:** 작업 1의 `ModelSettings.from_env`를 소비합니다. `AGENT_OPT_MODEL`은 OpenCode 모델 선택자, `OSS_SIM_IMAGE`는 upstream driver 입력으로 유지합니다. 전달 목록은 새 이름을 사용합니다.

- [ ] **1단계: 실패 테스트.** `test_cli_experience.py`에서 연구 plan의 새 이름만 주면 `model.configuration=ok`, 옛 이름만 주면 `error`와 키 비노출을 검사합니다. `test_menu.py`의 자식 환경에는 `AGENT_OPT_MODEL_API_KEY`만 있어야 합니다. `test_dev_environment.py`의 `validate_live`가 새 모델 ID를 전달하는지 확인하고 evaluator의 `OSS_SIM_IMAGE` 계약도 유지합니다.

```python
with patch.dict(os.environ, {"MODEL_ENDPOINT": "https://example.invalid/v1/chat/completions",
                             "MODEL_API_KEY": "legacy-secret"}, clear=True):
    result = collect_plan(research_plan, Registry())
    self.assertEqual(next(r["status"] for r in result["checks"]
                          if r["id"] == "model.configuration"), "error")
    self.assertNotIn("legacy-secret", json.dumps(result))
```

- [ ] **2단계: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`와 메뉴·개발환경 테스트에서 이전 소비자가 실패하는지 확인합니다.
- [ ] **3단계: 변경.** Python/TOML/JS/JSON 소비자와 fixture의 프로젝트 변수만 바꿉니다. `readiness.py` 조치, 메뉴 세션, `setup.validate_live`, `env_passthrough`, OpenCode 템플릿, evaluator Python override를 갱신합니다. `OSS_SIM_IMAGE`와 평가기의 키 비전달은 유지합니다. `MODEL_ENDPOINT|MODEL_BASE_URL|MODEL_ID|MODEL_API_KEY|CVDP_PYTHON` 검색에서 옛 이름은 과거 문서·거부 테스트·전환 안내에만 남아야 합니다.
- [ ] **4단계: 통과 확인.** `test_menu.py`, `test_cli_experience.py`, `test_dev_environment.py`, `test_demo_environment.py`, `test_network.py`를 `.venv/bin/python -m unittest discover -s tests -p <파일> -v`로 실행합니다.
- [ ] **5단계: 커밋.** status/diff/log와 변경 파일을 확인하고 `Propagate prefixed model settings to examples and diagnostics`로 커밋합니다.

### 작업 3: 공개 CLI 파서를 Typer로 교체

**파일:** `src/agent_optimizer/cli.py`, `tests/test_cli_experience.py`, `tests/test_progress.py`, `README.md`, `docs/development.md`, `docs/adding-components.md`; 생성 argv가 바뀔 때만 `src/agent_optimizer/setup_wizard.py`.

**계약:** `scripts/agent-opt`·`__main__`·테스트·TUI의 `main(argv: list[str] | None = None) -> int`를 유지합니다. `show(value) -> None`, `doctor() -> dict`, 기존 분기를 옮긴 `_dispatch(args) -> int`와 `Registry` 해석을 유지합니다. `--command-json`은 검증 후 `list[str]`로 바꿉니다. 잘못된 설정·진단은 2, 미완료 실행은 3, 중단은 130입니다.

- [ ] **1단계: 실패 테스트.** fixture에서 `init --command-json '["python", "agent.py", "--input", "{task_dir}"]'`가 정확한 harness 명령을 생성하는지 검사합니다. `--argv` 거부 전 데이터셋 미준비, 반복 `--dataset`·`--editable`·`--optimizer`, `doctor --plan examples/minimal/experiment.toml --json`의 단일 문서·읽기 전용, 잘못된 옵션의 stderr/코드 2, `--help`의 부작용 없음도 확인합니다.

- [ ] **2단계: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_cli_experience.py -v`에서 `--argv` 거부 테스트의 실패를 확인합니다.
- [ ] **3단계: 파서 교체.** Typer app 하나와 중첩 `datasets` app에 `plugins`, `doctor`, `datasets list/prepare`, `init`, `tui`, `run-session`, `agents`, `validate`, `plan`, `run`, `report`를 타입 선언으로 등록합니다. 인수는 `types.SimpleNamespace`를 통해 `_dispatch(args)`에 전달하며 callback에 실행 로직을 복제하지 않습니다. Typer 0.27은 Click을 내장하므로 예외 경계는 아래처럼 설정합니다.

```python
from types import SimpleNamespace
import typer
from typer._click import ClickException
from typer._click.core import Exit

app = typer.Typer(no_args_is_help=True)
dataset_app = typer.Typer()
app.add_typer(dataset_app, name="datasets")

def _invoke(command: str, **kwargs) -> int:
    return _dispatch(SimpleNamespace(command=command, **kwargs))

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    previous = sys.dont_write_bytecode
    if argv and argv[0] == "doctor":
        sys.dont_write_bytecode = True
    try:
        return typer.main.get_command(app).main(args=argv, prog_name="agent-opt",
                                                 standalone_mode=False) or 0
    except ClickException as exc:
        exc.show(file=sys.stderr)
        return exc.exit_code
    except Exit as exc:
        return exc.exit_code
    finally:
        sys.dont_write_bytecode = previous
```

`run` callback 예:

```python
@app.command("run")
def run_command(experiment: Path, output: Path | None = typer.Option(None, "--output")) -> int:
    return _invoke("run", experiment=experiment, output=output)
```

`init`의 `command_json: str | None = typer.Option(None, "--command-json")`, 반복 `dataset`·`editable`·`optimizer`는 `list[str] | None`으로 선언합니다. 기존 숫자 기본값과 `--yes`·경로·`--agent`·`--revision`·`--prompt-file`·`--evaluator`·`--metric`·`--direction`·`--harness`·`--optimizer-config`·`--scaffold-file`·`--target-file`을 유지합니다. `SimpleNamespace`에는 해당 분기의 속성을 모두 넣고 `command_json`만 파싱합니다. `doctor`는 `dataset`, `plan`, `project_root`, `json`, `model`을 채웁니다. `rerank`의 명시적 보류 오류와 doctor bytecode guard를 유지합니다.
- [ ] **4단계: 안내.** 사용 예제는 dash-prefixed Agent 옵션까지 JSON 문자열로 감싸 `--command-json`에 전달합니다. `scripts/dev.py`/bootstrap과 패키징 entry point는 유지합니다.
- [ ] **5단계: 확인.** `test_cli_experience.py`·`test_progress.py`·`test_plugin_contracts.py`·`test_dev_onboarding.py`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer --help`를 실행하고 `init`·`doctor`·`plan`·`datasets list`·`run`·`report` 및 TUI의 JSON stdout을 확인합니다.
- [ ] **6단계: 커밋.** status/diff/log 확인 후 `Migrate public CLI parsing to Typer`로 커밋합니다.

### 작업 4: Rich로 대화형 진행 표시

**파일:** `src/agent_optimizer/terminal_report.py`, `tests/test_progress.py`, 준비 표시 검사가 있으면 `tests/test_dev_onboarding.py`.

**계약:** `ProgressDisplay(stream=None).configure_budget(max_trials)`·`.start()`·`.__call__(event)`·컨텍스트 관리자·`PreparationStatus(name, stream=None)`을 유지합니다. 기본 출력은 stderr입니다.

- [ ] **1단계: 실패 테스트.** 비TTY `io.StringIO`와 `isatty()`가 참인 테스트 stream으로 진행 상태를 확인합니다. 비TTY 줄에는 iteration·사용/남은 예산·느린 과제 순서가 있고 제어 문자는 없어야 합니다. TTY는 Rich 색상·event 상태·정상/실패 종료 표시를 확인합니다. stdout JSON에는 진행 내용이 섞이지 않아야 합니다.

```python
class TtyBuffer(io.StringIO):
    def isatty(self):
        return True

def test_progress_uses_rich_only_for_tty(self):
    out = TtyBuffer()
    with ProgressDisplay(stream=out) as progress:
        progress.configure_budget(4)
        progress({"event": "trial_completed", "timestamp": "2026-09-24T10:00:00Z",
                  "task_id": "slow", "metrics": {"task_wall_time_seconds": 5.0}})
    self.assertIn("slow", out.getvalue())
```

- [ ] **2단계: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_progress.py -v`에서 새 TTY 색상 테스트가 실패하는지 봅니다.
- [ ] **3단계: 구현.** TTY에서만 Rich `Console(file=self.stream, force_terminal=True)`과 `Progress`를 사용합니다. 기존 잠금 내에서 이벤트를 갱신하고 예외 때도 `__exit__`에서 종료합니다. 비TTY 요약과 `PreparationStatus`의 완료/실패 문구는 그대로 두고 stdout/stderr 자동 redirect를 끕니다.
- [ ] **4단계: 통과 확인.** `test_progress.py`, `test_cli_experience.py`, `test_dev_onboarding.py`와 `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`에서 JSON stdout과 stderr 진행을 확인합니다.
- [ ] **5단계: 커밋.** status/diff/log 확인 후 `Use Rich for interactive progress rendering`으로 커밋합니다.

### 작업 5: 현행 안내와 frozen 프로젝트 검증

**파일:** `.env.example`, `README.md`, `docs/development.md`, `experiments/simple-feedback/README.md`, `examples/{ace-rtl,rtl-debugger}/README.md`, `docs/SOURCES.md`, 남은 fixture. 과거 `docs/verification.md` 기록은 수정하지 않습니다.

**계약:** 새 이름·환경의 인증정보·표준 `--command-json`·`uv.lock` 설치를 문서화합니다. 실제 모델 호출이나 공식 평가를 실행했다고 주장하지 않습니다.

- [ ] **1단계: 안내 갱신.** 현재 `MODEL_*` export·`--argv` 예제를 교체하고 별칭 없는 단절을 명시합니다. `docs/SOURCES.md`에는 Pydantic Settings/Typer/Rich 공식 출처와 소비 파일을 기록합니다. 옛 이름은 거부 테스트·과거 기록·전환 안내에만 남겨야 합니다. diff에서 인증 값·upstream pin 변경도 확인합니다.
- [ ] **2단계: 검증.** `uv sync --frozen --python 3.12 --extra dev`, `make doctor ARGS="--core"`, `make lint`, `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`, `.venv/bin/python -m build`를 실행합니다. 합성 fixture와 외부 실환경은 구분합니다.
- [ ] **3단계: 최종 점검.** `git diff --check`, `git status --short --branch`, `git diff`, `git log --oneline -10`, 기본 워크트리의 `git status --short --branch`·`git worktree list`를 확인하고 발견한 문제만 수정·재검증합니다.
- [ ] **4단계: 커밋.** 현행 문서와 필요한 최종 수정만 `Document prefixed configuration and modern CLI setup`으로 커밋합니다.
- [ ] **5단계: 전달.** 필요하면 `origin/main`과 비교하고 브랜치를 push한 뒤 `gh`로 PR을 만듭니다. 실제 검증 결과와 URL을 보고하고 병합 승인은 따로 받습니다.
