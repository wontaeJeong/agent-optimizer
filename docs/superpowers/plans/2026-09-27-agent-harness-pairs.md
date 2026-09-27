# Agent–Harness 선택 쌍 구현 계획

> **작업 에이전트:** 작업별 구현에는 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용하고 아래 체크박스를 추적한다.

**목표:** experiment TOML의 선택적 `[[pairs]]`로 실행할 Agent–Harness 프로필 쌍만 고르고 계획·예산·결과를 일치시킨다.

**구조:** `config.selected_pairs(spec)` 한 함수를 기본 전체 곱과 명시적 부분 집합의 단일 조회 지점으로 둔다. 로더가 설정을 실행 전에 검증하고, runner/doctor/plan은 동일한 목록을 사용한다. 설치 entry point나 별도 scheduler를 만들지 않는다.

**기술:** Python 3.11+, `tomllib`, `unittest`, 기존 TOML 설정/fixture runner.

**설계:** [승인된 설계](../specs/2026-09-27-agent-harness-pairs-design.md).

## 전역 제약

- 전용 worktree `.worktrees/agent-harness-pairs`, branch `feat/agent-harness-pairs`; 기본 checkout `main`을 수정하지 않는다. 작업 시작점은 명시적으로 fetch한 `origin/main`이다.
- `[[pairs]]`가 없으면 Agent-major 전체 곱, 모든 Agent가 모든 adapter를 지원해야 하는 기존 계약을 유지한다.
- `[[pairs]]`가 있으면 `agent=AgentSpec.id`, `harness=profile.id`의 두 필드만 허용하며 중복/빈 목록/알 수 없는 ID/지원 밖 쌍/미사용 Agent·프로필은 실행 전에 명시 오류다. 선언 순서가 실행 순서다.
- 선택 쌍만 group·trial·`plan.matrix`·예산 최소량에 반영한다. 원본/editable/private 경계·validation→test 순서·점수·nullable 사용량은 그대로 유지한다.
- TUI wizard 질문, CLI 옵션, 연구 Optimizer 연결, 외부 모델/Docker 실행을 추가하지 않는다. API-free fixture만 계약 증거다.

## 파일 책임 지도

- `src/agent_optimizer/config.py`: TOML 키와 `selected_pairs(spec) -> list[tuple[AgentSpec, dict]]` 검증·조회.
- `src/agent_optimizer/runner.py`: preflight 예산/그룹 수, resolved Agent와 선택 프로필의 실제 그룹 실행.
- `src/agent_optimizer/readiness.py`: `doctor --plan` trial 예약량.
- `src/agent_optimizer/cli.py`: `agent-opt plan` matrix.
- `tests/test_pairs.py`: 설정 오류/기본 호환·sparse 실제 fixture/doctor/plan/증거.
- `docs/architecture.md`, `docs/adding-components.md`, `docs/status.md`, `docs/FUTURE.md`: 사용 예와 구현·보류 경계.

---

### Task 1: 설정과 쌍 선택 단일 계약

**Files:**
- Modify: `src/agent_optimizer/config.py:144-209`
- Create: `tests/test_pairs.py`

**Interfaces:**
- Consumes: `load_agent`, `load_experiment`, AgentSpec.id/supported_harnesses, profile `id`/`adapter`.
- Produces: `selected_pairs(spec: dict) -> list[tuple[AgentSpec, dict]]`, 명시적 `pairs`는 TOML 원본에 유지.

- [ ] **Step 0: 작업 환경 준비.** `make setup-core`로 이 전용 worktree의 `.venv`와 합성 최소 데모를 준비한다. 실패하면 환경 원인을 조사하고 기준을 기록한 뒤 RED 테스트로 간다.
- [ ] **Step 1: 설정 실패/기본 테스트부터 작성.** `test_project()`의 임시 복사본에서 `examples/minimal/harness.toml` 내용을 복사하고 `id="fixture-alt"`만 바꿔 `examples/minimal/fixture-alt.toml`에 저장한다. 임시 experiment TOML의 `harnesses`에 이를 추가한다. 다음 입력/출력을 테스트한다:

```python
spec = load_experiment(experiment_path)
assert [(a.id, h["id"]) for a, h in selected_pairs(spec)] == [
    ("rtl-solo", "fixture"), ("rtl-solo", "fixture-alt"),
    ("rtl-team", "fixture"), ("rtl-team", "fixture-alt")]
# [[pairs]]를 다음 순서로 선언한 별도 입력:
# agent="rtl-team", harness="fixture-alt"; agent="rtl-solo", harness="fixture"
assert [(a.id, h["id"]) for a, h in selected_pairs(spec)] == [
    ("rtl-team", "fixture-alt"), ("rtl-solo", "fixture")]
```

  `pairs=[]`, `pairs="bad"`, mapping 대신 문자열, extra key, 빈/비문자 값, 같은 쌍 중복, 알 수 없는 Agent/profile ID, 선언만 한 unused Agent/profile, unsupported adapter 조합은 각각 `ConfigurationError`를 기대한다. `supported_harnesses`가 다른 프로필 adapter를 지원하지 않아도 **선택한** 쌍만 지원하면 허용하고, `pairs` 없이는 기존 전체 조합 오류를 유지한다. 실제 fixture manifest의 지원 ID/프로필 ID를 사용한다.
- [ ] **Step 2: RED 관측.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_pairs.py -v` → `pairs`가 미지원이고 `selected_pairs`가 없는 원인으로 실패해야 한다.
- [ ] **Step 3: 최소 구현.** `load_experiment`의 top-level 허용 키에 `pairs`를 추가한다. profiles/agents를 읽은 뒤 `data["_profiles"] = profiles`를 먼저 설정하고 `selected_pairs(data)`로 검증한다. 기존 이중 루프 호환성 검사를 이 함수에 통합한다. `pairs`가 없으면 전체 곱 순서를 유지하고, 있는 경우 아래 규칙으로 정확한 목록을 조립한다:

```python
def selected_pairs(spec: dict) -> list[tuple[AgentSpec, dict]]:
    agents, profiles = spec["_agents"], spec["_profiles"]
    if "pairs" not in spec:
        pairs = [(agent, profile) for agent in agents for profile in profiles]
    else:
        raw = spec["pairs"]
        if not isinstance(raw, list) or not raw:
            raise ConfigurationError("pairs must be a nonempty list")
        by_agent = {agent.id: agent for agent in agents}
        by_profile = {profile["id"]: profile for profile in profiles}
        pairs = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ConfigurationError("Each pair must declare agent and harness IDs")
            only_keys(item, {"agent", "harness"}, "pair")
            key = (item.get("agent"), item.get("harness"))
            if any(type(value) is not str or not value for value in key):
                raise ConfigurationError("pair.agent and pair.harness require IDs")
            if key in seen or key[0] not in by_agent or key[1] not in by_profile:
                raise ConfigurationError("Duplicate or unknown Agent–Harness pair")
            seen.add(key)
            pairs.append((by_agent[key[0]], by_profile[key[1]]))
        if ({agent.id for agent, _ in pairs} != set(by_agent)
                or {profile["id"] for _, profile in pairs} != set(by_profile)):
            raise ConfigurationError("Remove unselected agents and harnesses")
    for agent, profile in pairs:
        if profile["adapter"] not in agent.supported_harnesses:
            raise ConfigurationError(f"{agent.id} does not support {profile['adapter']}")
    return pairs
```

  이 함수는 매번 현재 spec의 Agent/Profile을 읽는다. 기존 테스트가 `load_experiment` 뒤 `_agents`나 `_profiles`를 수정해도 기본 전체 곱이 최신 상태로 계산되어야 한다.
- [ ] **Step 4: GREEN·커밋.** 위 focused suite와 `test_core.py`를 실행하고 상태/diff/log를 검토해 두 파일만 커밋한다. 메시지: `실험 설정의 Agent–Harness 선택 쌍 검증`.

### Task 2: 실행·예산·계획을 같은 쌍으로 통일

**Files:**
- Modify: `src/agent_optimizer/runner.py:347-435`
- Modify: `src/agent_optimizer/readiness.py:219-230`
- Modify: `src/agent_optimizer/cli.py:730-740`
- Modify: `tests/test_pairs.py`

**Interfaces:**
- Consumes: Task 1의 `selected_pairs(spec) -> list[tuple[AgentSpec, dict]]`.
- Produces: selected pair count 기반 예산·`planned_groups`, 선언 순서의 GroupRunner 실행·`plan.matrix`.

- [ ] **Step 1: 실제 fixture 행동 테스트부터 작성.** 위 2-Agent/2-profile 실험에 명시적 `[[pairs]]`를 두고 default와 sparse 실행의 `group` 목록, `trials_used`, `manifest.json`의 실험 선언, `summary.planned_groups`, `agent-opt plan` JSON matrix를 비교한다. stage-local history와 frozen selection을 선택한 그룹 두 개에서 확인한다. budget이 두 쌍에 필요한 최소량이면 sparse plan과 preflight는 ready, 같은 예산의 전체 곱은 blocked인지 검증한다. `doctor --plan`은 소스/도구 등 다른 체크가 실패할 수 있으므로 `budget.trials` 체크를 직접 검사한다.

```python
expected = [("rtl-team", "fixture-alt"), ("rtl-solo", "fixture")]
assert [(row["agent_id"], row["harness_id"]) for row in summary["groups"]] == expected
assert summary["planned_groups"] == 2
assert [(row["agent"], row["harness"]) for row in plan["matrix"]] == expected
assert json.loads((run / "manifest.json").read_text())["experiment"]["pairs"] == [
    {"agent": "rtl-team", "harness": "fixture-alt"},
    {"agent": "rtl-solo", "harness": "fixture"}]
```

- [ ] **Step 2: RED 관측.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_pairs.py -v` → 4개 그룹으로 실행되거나 budget/plan matrix가 전체 곱이어서 실패해야 한다.
- [ ] **Step 3: 최소 구현.** `runner.preflight`와 `_budget_check`의 `len(_agents)*len(_profiles)`을 `len(selected_pairs(spec))`으로, summary의 `planned_groups`도 동일하게 바꾼다. resolved Agent는 전부 잠그되 `resolved_by_id = {agent.id: agent for agent in resolved_agents}`를 만들고 그룹 루프에서 `for source, profile in selected_pairs(spec): agent = resolved_by_id[source.id]` 순서로 실행한다. `cli.py`의 plan matrix는 `selected_pairs(spec)`에서 출력한다. 동일 함수 import를 사용하고 두 번째 group filtering abstraction은 만들지 않는다.

```python
resolved_by_id = {agent.id: agent for agent in resolved_agents}
for source, profile in selected_pairs(spec):
    agent = resolved_by_id[source.id]
    budget.remaining()
    group = GroupRunner(spec, agent, profile, root / agent.id / profile["id"],
                        registry, budget, events)
```

  기존 `summary["groups"]`의 시작 row/partial-failure 기록, stage boundaries, final artifact를 이 루프에서도 빠짐없이 유지한다. 선호되는 최소 수정은 기존 루프 본문을 그대로 두고 바깥 이중 루프만 치환하는 것이다.
- [ ] **Step 4: GREEN·커밋.** `test_pairs.py`, `test_core.py`, `test_run_lifecycle.py`, `test_progress.py`를 실행한다. 그룹 수·예산·report 경계를 확인하고 네 변경 파일만 diff/status/log로 검토해 커밋한다. 메시지: `선택 쌍 기준 실행과 계획 예산 통일`.

### Task 3: 사용 안내와 전체 회귀

**Files:**
- Modify: `docs/architecture.md:18-25`
- Modify: `docs/adding-components.md:95-105`
- Modify: `docs/status.md:19-40`
- Modify: `docs/FUTURE.md:1-31`
- Modify: `README.md:267-276`
- Test: `tests/test_pairs.py` (회귀가 드러낸 경계에만 추가)

**Interfaces:**
- Consumes: Task 1/2의 TOML schema, 선택 실행/예산/plan matrix.
- Produces: 복사 가능한 사용자 예와 실제 검증 범위 설명.

- [ ] **Step 1: 정확한 문서화.** `docs/adding-components.md`의 Harness 안내에 `[[pairs]] agent="rtl-solo" harness="fixture"` 예와 `harness`가 프로필 ID임을 명시한다. README·architecture·status는 기본 전체 곱과 선택 가능 쌍을 구분하고 FUTURE에서는 **임의 pair matrix가 보류**라는 이전 문장을 수정한다. 실제 테스트/실행 근거 없이 외부 Agent 성능 성공은 쓰지 않는다.
- [ ] **Step 2: 전체 검증.** Task 1에서 준비한 `.venv`로 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`, `make lint`, `PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml`(기본 7 trial), `PYTHONPATH=src .venv/bin/python -m agent_optimizer plan examples/minimal/experiment.toml`(기본 matrix)을 실행한다. `make setup-core` 자체도 Task 1에서 7-trial 합성 데모를 실행했다. 새 두 쌍 예제 테스트는 API-free이며 실모델/공식 CVDP 근거가 아니라고 기록한다.
- [ ] **Step 3: 자체 점검·커밋.** `git status --short --branch`, `git diff --check`, `git diff`, `git log --oneline -10`을 확인해 문서와 필요한 회귀만 커밋한다. 메시지: `실험별 Agent–Harness 선택 쌍 안내`.

## 완료·인계

작업별 리뷰에서 중요 지적은 수정한 뒤 새 커밋으로 남긴다. 전체 브랜치 리뷰와 최신 `origin/main` 기준 diff/CI 검증 후 push·PR을 생성한다. TUI/웹의 UI는 바꾸지 않으므로 캡처 요구를 이 작업에 적용하지 않는다. PR 생성 후 해당 PR의 병합은 별도 사용자 승인을 따른다.
