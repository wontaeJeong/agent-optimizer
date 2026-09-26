# Claude Code–CVDP 실검증 구현 계획

> **작업 에이전트:** 작업별 실행에는 `superpowers:executing-plans`를 사용한다. 항목의 `- [ ]`는 완료 시 갱신한다.

**목표:** wheel에서 선택할 수 있는 Claude Code 하네스를 구현하고 DeepSeek Anthropic 호환 API와 공식 CVDP의 최대 4-trial 실실행을 기록한다.

**구조:** 공통 실행·평가 계약은 유지하고 `claude_code`만 코어에 추가한다. ACE 지침과 한정 예산 구성은 예제에 둔다. 실행 자격증명은 앱 설정에 저장하지 않고 명시적으로 로드한 셸 환경에서 전달한다.

**기술:** Python 3.11+, unittest, Typer, Claude Code CLI 2.1.261(예제 pin), DeepSeek Anthropic 호환 엔드포인트, 기존 CVDP 공식 Docker 평가.

**설계:** [승인된 설계](../specs/2026-09-26-claude-code-cvdp-validation-design.md).

## 전역 제약

- 기본 checkout의 `main`을 수정하지 않는다. 기존 `.worktrees/mvp-harness-validation-controls`와 `feat/mvp-harness-validation-controls`를 계속 사용한다.
- 내장 하네스의 외부 CLI 버전은 기록만 하고, ACE 예제 프로필만 `2.1.261`과 일치할 때 실행한다. wheel에는 Claude 실행 파일을 포함하지 않는다.
- CVDP 고정 소스·해시·평가 로직을 변경하지 않는다. 원본 Agent·private 평가 자료·점수 계산은 최적화로 수정하지 않는다.
- 모델 호출의 첫 상한은 4 trial, 공개 train 1개·validation 1개, `final_test=false`; 개선을 보장하거나 upstream 재현으로 표시하지 않는다.
- `AGENT_OPT_MODEL_API_KEY` 값은 커밋·명령 argv·검증 문서·PR 본문에 넣지 않는다. 앱이 `.env`를 자동 로딩하지 않는다. 병렬 scheduler와 resume는 손대지 않는다.

## 파일 책임 지도

- `src/agent_optimizer/harnesses/claude_code.py`: Claude argv, 외부 CLI 버전 확인, 결과 이벤트 해석과 partial 사용량.
- `src/agent_optimizer/registry.py`, `contracts.py`, `config.py`, `setup_wizard.py`: 내장 등록·기능 표시·선택·예제 pin 설정의 최소 배선.
- `examples/ace-rtl/adapter.py`, `source.toml`, 신규 `harness-claude.toml`, `experiment-claude.toml`: ACE 지침 재사용과 별도 실험.
- `examples/ace-rtl/environment/lifecycle.py`, `checks.py`: 별도 예제 선택 시 준비 완료 검사와 기존 runner 호출 재사용.
- `tests/test_claude_code.py`, 관련 기존 CLI/ACE 테스트: 외부 네트워크 없이 계약·분리·패키징 경로 검증.
- `docs/SOURCES.md`, `docs/status.md`, `docs/verification.md`, `examples/ace-rtl/README.md`: 공식 근거, 실제 관측 결과와 재현 명령.

---

### Task 1: 범용 Claude CLI 실행 계약

**Files:**
- Create: `src/agent_optimizer/harnesses/claude_code.py`
- Create: `tests/test_claude_code.py`

**Interfaces:**
- Consumes: `RunRequest`, `ExecutionResult`, `CommandHarness.run`, `process.execute`.
- Produces: `ClaudeCodeHarness.argv(request) -> list[str]`, `ClaudeCodeHarness.run(request) -> ExecutionResult`; 프로필의 선택적 `required_cli_version: str`.

- [ ] **Step 1: 실패하는 실행·이벤트 계약 테스트 작성.** `tests/test_claude_code.py`에서 임시 workspace의 `RunRequest`를 만들고 `ClaudeCodeHarness.argv`에 `claude`, `-p`, `--output-format stream-json`, prompt가 분리된 argv로 들어가는지 검사한다. `subprocess.run`으로 `claude --version`을 모의하고 `agent_optimizer.harnesses.command.execute`를 모의해 `stdout.log`에 아래 결과를 기록한 뒤 결과 상태/partial 지표를 검사한다:

```python
{"type": "result", "subtype": "success", "is_error": False,
 "usage": {"input_tokens": 12, "output_tokens": 3}, "total_cost_usd": 0.01}
```

  `result` 누락, `subtype=error_during_execution`, `is_error=true`, 비정상 종료, version mismatch, CLI 누락, 잘못된 JSON, 음수/NaN 비용, timeout의 별도 검사도 둔다. 모의 토큰은 `harness_reported_io_tokens=15`, 비용은 `harness_reported_cost_usd=0.01`, 전체 `agent_tokens=None`이어야 한다. 모델 출력 텍스트·자격증명을 오류 detail에 복사하지 않는다.

- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_claude_code.py -v` → 모듈 미구현 실패.

- [ ] **Step 3: 최소 구현.** `CommandHarness`를 상속하고 `run`에서 `subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5, check=False)`로 관측 버전을 가져와 `logs/cli-version.txt`에 적는다. `required_cli_version`이 있을 때만 버전을 비교하며 차이는 자격증명 없이 명시적으로 실패시킨다. local runtime만 지원하고 Docker 요청은 명시적 `UnavailableError`로 거부한다. `argv`는 `claude -p <prompt> --output-format stream-json --verbose --max-turns 8 --allowedTools Read,Write,Edit`의 배열이다. `super().run`이 반환한 원본 stdout의 JSONL에서 완료 `result` 하나의 `subtype`과 `is_error`를 확인하고 유한한 숫자만 partial 사용량으로 기록한다. 성공 result가 없거나 모델/인증 오류 이벤트가 있으면 `infrastructure_error`와 nullable 점수 경로를 선택한다. 실제 CLI 버전 출력과 stdout 형식을 2.1.261 실제 실행 전에 `claude --help`/공식 문서에 대조한다.

```python
class ClaudeCodeHarness(CommandHarness):
    def argv(self, request: RunRequest) -> list[str]:
        if request.profile.get("runtime", {}).get("kind", "local") != "local":
            raise UnavailableError("claude_code requires a local runtime")
        return ["claude", "-p", request.prompt, "--output-format", "stream-json",
                "--verbose", "--max-turns", "8", "--allowedTools", "Read,Write,Edit"]

    def run(self, request: RunRequest) -> ExecutionResult:
        version = subprocess.run(["claude", "--version"], capture_output=True,
                                 text=True, timeout=5, check=False)
        observed = version.stdout.strip().split(" ", 1)[0]
        required = request.profile.get("required_cli_version")
        if version.returncode or (required and required != observed):
            raise UnavailableError("Claude Code CLI version unavailable or mismatched")
        request.logs.mkdir(parents=True, exist_ok=True)
        (request.logs / "cli-version.txt").write_text(observed + "\n")
        result = super().run(request)
        finals, invalid = [], 0
        for line in Path(result.stdout_path).read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                invalid += 1
                continue
            if not isinstance(event, dict):
                invalid += 1
            elif event.get("type") == "result":
                finals.append(event)
        final = finals[0] if len(finals) == 1 else {}
        usage = final.get("usage") if isinstance(final.get("usage"), dict) else {}
        tokens = [usage.get(key) for key in ("input_tokens", "output_tokens")]
        valid_tokens = all(type(value) is int and value >= 0 for value in tokens)
        cost = final.get("total_cost_usd")
        valid_cost = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
        result.metrics.update(harness_reported_io_tokens=sum(tokens) if valid_tokens else None,
                              harness_reported_cost_usd=cost if valid_cost else None,
                              unparsed_event_lines=float(invalid))
        if result.status == "completed" and (not final or final.get("subtype") != "success"
                                              or final.get("is_error")):
            result.status = "infrastructure_error"
            result.detail = "Claude Code did not emit a successful result; see raw trace"
        return result
```

  CLI 누락 `OSError`, version timeout도 자격증명 노출 없이 infrastructure error로 전달한다. 최종 `result`의 usage에 없는 토큰을 0으로 채우지 않는다.

- [ ] **Step 4: 통과 확인과 커밋.** 위 테스트와 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_adapters.py -v`를 실행한다. `git status`, `git diff`, `git log --oneline -10` 확인 후 두 파일만 커밋한다. 메시지: `Claude Code 실행 결과와 부분 사용량 해석`.

### Task 2: wheel 선택과 예제 버전 선언 배선

**Files:**
- Modify: `src/agent_optimizer/registry.py:9-15,83-96`
- Modify: `src/agent_optimizer/contracts.py:156-170`
- Modify: `src/agent_optimizer/config.py:164-180`
- Modify: `src/agent_optimizer/setup_wizard.py:19-42`
- Modify: `tests/test_claude_code.py`

**Interfaces:**
- Consumes: Task 1의 `ClaudeCodeHarness`, `required_cli_version`.
- Produces: `Registry.resolve("harnesses", "claude_code")`, `init --harness claude_code`에서 생성한 local profile.

- [ ] **Step 1: 등록·프로필 실패 테스트 추가.** `Registry().resolve("harnesses", "claude_code") is ClaudeCodeHarness`, `supports_generated_profile(ClaudeCodeHarness)`가 참인지 확인한다. 예제 아닌 wheel 사용자 생성 프로필에는 `required_cli_version`이 없어야 한다. 프로필에 `required_cli_version="2.1.261"`을 입력한 `load_experiment`가 허용하고, 숫자·빈 문자열은 `ConfigurationError`로 거부해야 한다. 이 상태에서 테스트를 실행해 실패를 확인한다.
- [ ] **Step 2: 최소 배선.** `Registry.factories["harnesses"]`에 `"claude_code": ClaudeCodeHarness`를 추가하고 reserved 항목에서 제거한다. `BUILTIN_HARNESSES`에 `claude_code`의 부분 이벤트 trace·전체 사용량 미검증 능력을 기재한다. `config.load_experiment`의 허용 프로필 키에 `required_cli_version`을 추가하고 비어 있지 않은 문자열인지 검증한다. `setup_wizard.supports_generated_profile`에 `ClaudeCodeHarness`를 추가한다. CLI의 데이터셋 목록·설치 entry point는 변경하지 않는다.

```python
# registry.py: 기존 dict의 항목만 추가
"harnesses": {"command": CommandHarness, "fixture": FixtureHarness,
              "opencode": OpenCodeHarness, "claude_code": ClaudeCodeHarness},
# config.py: profile을 읽은 직후
required = profile.get("required_cli_version")
if required is not None and (not isinstance(required, str) or not required.strip()):
    raise ConfigurationError("required_cli_version must be a nonempty string")
# setup_wizard.py
return requires_command(adapter) or adapter in {FixtureHarness, OpenCodeHarness, ClaudeCodeHarness}
```
- [ ] **Step 3: 통과·wheel 독립 검사·커밋.** 관련 unittest와 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_installed_cli.py -v`를 실행한다. `.venv/bin/python -m build --wheel` 뒤 배포 wheel에서 `agent-opt plugins`에 `claude_code`가 보이는지 확인한다. diff/status/log 검토 후 배선과 테스트만 커밋한다. 메시지: `Claude Code 하네스를 wheel 선택 목록에 등록`.

### Task 3: ACE–Claude 전용 4-trial 프로필

**Files:**
- Modify: `examples/ace-rtl/adapter.py:1-43`
- Modify: `examples/ace-rtl/source.toml:1-11`
- Create: `examples/ace-rtl/harness-claude.toml`
- Create: `examples/ace-rtl/experiment-claude.toml`
- Modify: `examples/ace-rtl/environment/lifecycle.py:57-76`
- Modify: `examples/ace-rtl/environment/checks.py:104-120`
- Modify: `tests/test_claude_code.py`

**Interfaces:**
- Consumes: Task 1/2의 하네스·선택적 pin; 기존 `with_ace_guidance`, `lifecycle.inspect`와 `checks.live`.
- Produces: `ACEClaudeCode(ClaudeCodeHarness)`와 `agent-opt run examples/ace-rtl/experiment-claude.toml`.

- [ ] **Step 1: 예제 선택 실패 테스트.** 기존 `source.toml`이 원래 OpenCode와 새 `ace_claude_code`를 모두 허용하는지, 새 실험이 `max_trials=4`, `final_test=false`, `iterations=1`, `required_cli_version="2.1.261"`인지 `load_experiment`로 검사한다. 별도 프로필의 launcher는 다른 TOML 경로·출처를 거부하고, 평가 준비가 실패하면 실제 Claude CLI 호출 없이 중단하는 mock 검사를 둔다. 첫 실행은 누락된 파일/등록 때문에 실패해야 한다.
- [ ] **Step 2: 예제와 생명주기 최소 수정.** `ACEClaudeCode.run`은 `super().run(with_ace_guidance(request))`로 역할 지침을 유지한다. 별도 launcher는 승인된 `experiment-claude.toml`일 때 기존 `lifecycle.inspect`의 CVDP 자산 검사와 `checks.live`의 공통 실행 경로를 사용한다. `lifecycle.run(root, experiment_file="experiment.toml")`을 추가하고 OpenCode 경로에서만 `setup.validate_live()`로 OPENCODE_CONFIG/모델을 설정한다. Claude 경로는 `ANTHROPIC_AUTH_TOKEN`·`ANTHROPIC_BASE_URL`·`ANTHROPIC_MODEL` 존재를 비밀값 출력 없이 확인한다. `checks.live(lock, iterations=None, experiment_file="experiment.toml")`이 해당 실험을 읽고 Docker OpenCode 프로필에만 agent 이미지 ID를 설정하도록 한다. 새 TOML은 기존 `datasets/ace-demo/tasks.json`과 공식 `cvdp` evaluator, simple_feedback `iterations=1`, `file="skills/ace-rtl/references/role-guidance.md"`, train/validation 선택과 4-trial 예산을 사용한다. 외부 ACE/CVDP SHA를 갱신하지 않는다.

```python
# adapter.py: 기존 with_ace_guidance를 그대로 재사용
class ACEClaudeCode(ClaudeCodeHarness):
    def run(self, request):
        return super().run(with_ace_guidance(request))

# checks.py: 기존 호출도 동일한 기본 인수로 유지
def live(lock, iterations=None, experiment_file="experiment.toml"):
    spec = load_experiment(ROOT / "examples/ace-rtl" / experiment_file)
    if iterations is not None:
        if type(iterations) is not int or not 1 <= iterations <= 20:
            raise ConfigurationError("Iterations must be an integer from 1 to 20")
        spec["stages"][0]["config"]["iterations"] = iterations
    count = spec["stages"][0]["config"]["iterations"]
    if {t.split for t in spec["_tasks"]} != {"train", "validation"} or len(spec["_tasks"]) != 2:
        raise ConfigurationError("Live demo needs prepared train/validation tasks; rerun setup")
    spec["budget"]["max_trials"] = 2 * (count + 1)
    spec["budget"]["max_wall_time_seconds"] = (2 * (count + 1) * spec["budget"]["trial_timeout_seconds"]
                                                   + count * 60 + 180)
    for profile in spec["_profiles"]:
        if profile.get("runtime", {}).get("kind") == "docker":
            profile["runtime"]["image"] = lock["images"]["agent"]["id"]
    with ProgressDisplay() as progress:
        progress.configure_budget(spec["budget"]["max_trials"])
        root, summary = run_experiment(spec, Registry(), ROOT / "runs/dev-live", on_event=progress)
    print(json.dumps({"status": summary["status"], "results": str(root)}))
    return 0
```

  예제 TOML의 핵심 값은 아래와 같다(프로필·플러그인 경로는 바로 위 파일 책임 지도의 경로를 쓴다):

```toml
# harness-claude.toml
id = "ace-claude-code"
adapter = "ace_claude_code"
allow_local = true
required_cli_version = "2.1.261"
[runtime]
kind = "local"

# experiment-claude.toml의 변경 지점
name = "ace-rtl-claude-cvdp-demo"
benchmark = "datasets/ace-demo/tasks.json"
final_test = false
[budget]
max_trials = 4
[[stages]]
id = "feedback"
optimizer = "simple_feedback"
[stages.config]
file = "skills/ace-rtl/references/role-guidance.md"
iterations = 1
```
- [ ] **Step 3: 통과·커밋.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_claude_code.py -v`, `-p test_cli_experience.py`, `-p test_integrations.py`를 실행한다. 구분된 예제 파일과 생명주기만 검토·커밋한다. 메시지: `ACE 스킬의 Claude Code 실험 프로필 추가`.

### Task 4: 실제 DeepSeek–Claude–CVDP 실행과 범위 기록

**Files:**
- Modify: `examples/ace-rtl/README.md`
- Modify: `docs/SOURCES.md`
- Modify: `docs/status.md`
- Modify: `docs/verification.md`
- Modify: `tests/test_claude_code.py` (실제 CLI가 드러낸 계약 차이에 대한 회귀가 필요한 경우)

**Interfaces:**
- Consumes: Task 3의 실행 가능한 4-trial 프로필.
- Produces: 실제 명령·모델·CLI 버전·CVDP 원시 채점 증거와 nullable/partial 보고.

- [ ] **Step 1: 코어·평가 자산 준비.** `make doctor-core`로 독립 워크트리를 확인한 뒤 `make setup`과 `make doctor`, `make smoke`로 고정 ACE 소스·CVDP·OSS Docker 평가를 준비·검증한다. Docker/다운로드 실패를 모델 성공으로 대체하지 않는다. 키 값이나 `.env` 본문은 터미널/문서에 출력하지 않는다.
- [ ] **Step 2: 인증 환경을 셸에서만 설정.** 사용자 로컬 `.env`의 기존 `AGENT_OPT_MODEL_*` 설정을 해당 실행 셸에 불러와 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`, `ANTHROPIC_AUTH_TOKEN`을 기존 DeepSeek 키에 연결한다. `ANTHROPIC_MODEL=deepseek-flash`와 필요한 Claude 기본 모델 변수를 DeepSeek 공식 연동 문서에 맞춰 설정한다. `ANTHROPIC_API_KEY`처럼 다른 provider 키가 충돌하면 CLI 호출 전에 환경만 정리한다. 인증 값·원본 `.env`를 코드·로그·PR에 붙이지 않는다.
- [ ] **Step 3: 작은 실실행.** `PYTHONPATH=src .venv/bin/python -m agent_optimizer doctor --plan examples/ace-rtl/experiment-claude.toml --json`과 `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/ace-rtl/experiment-claude.toml`을 차례로 실행한다. `run_dir`의 `events.jsonl`, `summary.json`, 공식 CVDP raw 결과와 `report.html`에서 진짜 모델 호출/과제 산출물/두 split의 유효성/선택 근거를 확인한다. 네트워크·계정·평가 실패는 차단 사유와 실제 완료 범위를 기록하고 성공으로 주장하지 않는다.
- [ ] **Step 4: 문서·검증.** 실제 관측값만 날짜와 환경·모델·CLI 버전·최대 예산·누락 지표와 함께 `docs/verification.md`에 작성하고 `status.md`, `SOURCES.md`, 예제 README를 갱신한다. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`로 회귀 검사한다. 보고서의 민감값 포함 여부와 diff/status/log를 확인한 뒤 문서·필요한 회귀만 커밋한다. 메시지: `DeepSeek·Claude Code·CVDP 실검증 근거 기록`.

## 완료·인계

문서가 승인된 첫 묶음의 구현·실행이 끝나면 커밋을 푸시하고 기존 PR이 없으면 PR을 생성한다. UI/UX 변경인 하네스 선택지는 변경 전·후 캡처와 재현 방법을 PR에 넣거나 캡처 불가 사유를 명시한다. 병렬화는 다른 작업 브랜치에서 진행하므로 충돌 파일을 임의 병합하지 않는다. 이후 별도 설계·계획으로 세 연구 Optimizer 실검증, 실행 이력 조회, Agent–Harness 조합 선택을 차례로 다룬다.
