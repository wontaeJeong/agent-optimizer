# C — 작업 범위 명세 준수·코드 품질 리뷰

확인일: 2026-10-01. 대상: `edbd2b8c7b05bdd63c352d02a7adf7652168d197` →
`4fd8af1d8864c21f14a3e7f06508bba412ce99e7`.

**명세 verdict: 부분 충족, Important 보완 필요. 코드 품질 verdict: 수정 후 재검토 필요.**
Critical 0건 / Important 2건 / Minor 2건이다. registry·CLI·native profile loader의 최종 연결은
F 범위로 제외했다. 해당 연결의 부재 자체를 C 결함으로 판정하지 않았다.

## 검토 근거·검증 수준

- 지정 brief `C_NATIVE_ACE_CVDP.md`, 구현 보고서 `final-mvp-c-20261001.md`, 제공 diff를 먼저 읽고
  변경 코드·기존 제품 계약/client/evaluator와 대조했다.
- 실제 upstream `external/ACE-RTL`의 HEAD는 `fead921f18bb57345b5a41ef93ba625be208e99c`이며
  `git status --short` 출력은 비어 있었다. 그 checkout의 `cli.py`, `llm.py`,
  `FocusedDebugger`, `FreshStartCoordinator`, `LLMClient`, `RTLRuleAdvisor`를 대조했다.
- `docs/SOURCES.md`의 ACE/CVDP/HF 고정 출처와 데이터 SHA-256을 대조했다.
  실제 pinned row를 사용하는 테스트의 선택·지원 판정·모델 입력·제출물 검증 코드를 읽었다.
  302개 원본 row 전체의 통계를 독립 재계산하거나 실제 시뮬레이터 판정을 수행하지는 않았다.
- 보고된 93개 테스트·Ruff 통과는 기존 수행 보고서의 증거다. 이번 리뷰에서는 테스트를 재실행하지 않았고,
  실모델·다운로드·설치·Docker 평가·하위 에이전트를 실행하지 않았다.
- 변경은 이 리뷰 문서에 한정한다. 소스 수정·커밋·푸시·PR 생성은 수행하지 않았다.

## Findings

### Important I1 — 일반 예외 종료 시 실제 모델 요청·usage가 최종 sidecar에서 사라진다

**위치:** `examples/ace-rtl/native_worker.py:33–39`,
`examples/ace-rtl/native_adapter.py:171–181`.

**근거:** `RoleTransport.call`은 요청 시작/완료를 `native-requests.json`에 기록한다
(`native_bridge.py:74–104`). 그러나 worker의 일반 `Exception` 분기는 초기 sidecar의
`requests=[]`, `usage_status="unreported"`를 그대로 두고 상태만 `infrastructure_error`로 바꾼다.
adapter는 상태가 `started`일 때만 요청 journal을 복구하므로, 이 종료에서는 복구를 건너뛴다.

**발생 경로:** 정상 API 응답을 받은 뒤 다중 target의 일부 section이 누락되거나 Markdown fence가
포함되면 `parse_outputs`가 `ConfigurationError`를 발생시킨다
(`native_bridge.py:187`, `native_cvdp.py:90–103`). 이때 모델 요청과 응답 token usage는 실제로
존재하지만 최종 `native-execution.json`에는 0건/미보고로 남는다. evaluator 예외 등에도 동일하다.
완료 iteration은 progress에서 복구하더라도 요청은 복구되지 않는다.

**영향·명세:** brief §6의 실제 role/request status/duration/usage 증거와 실패 시 보존 요구를
충족하지 못한다. F/D가 sidecar를 소비하면 실제 호출을 누락한 실행 보고서를 만든다.

**보완 방향:** 모든 worker 종료 분기에서 요청 journal을 일관되게 병합하고 usage 상태를 다시 계산해야 한다.
완료된 요청 뒤 출력 검증 실패 및 evaluator 예외를 거치는 worker→adapter 경로에서 보존 여부를 확인할 필요가 있다.

### Important I2 — outer timeout 이후 정리 시간이 iteration 수에 비례하여 별도로 누적된다

**위치:** `examples/ace-rtl/native_adapter.py:100–108, 169–170`.
연관 기존 구현: `examples/ace-rtl/evaluator.py:14–31`.

**근거:** worker 실행에는 잔여 deadline을 전달하지만, `finally`의 `cleanup_evaluators`에는
deadline·전체 cleanup 예산이 없다. 모든 iteration의 network marker를 순회하면서 이미 정상 정리된
network까지 다시 `cleanup_network`로 처리한다. 이 helper는 각 `docker ps`, container별 `docker rm`,
`docker network rm`에 각각 최대 15초를 허용한다. `run_worker` 종료 정리의 `ps` 진단과 wait 시간도 별도다.

**발생 경로:** 여러 iteration 후 outer timeout/취소가 발생하고 Docker daemon의 정리 요청이 지연되면,
worker가 종료된 뒤에도 marker마다 최대 15초 이상의 지연이 순차 누적된다. 완료된 network에도
조회/삭제를 다시 시도하므로 정상 실행 종료에서도 추가 시간이 생긴다.

**영향·명세:** brief §1의 outer 상한과 구현 보고서 `final-mvp-c-20261001.md:119`의
잔여 예산 계약이 adapter 반환까지 적용되지 않는다. 기존 코어는 adapter 반환을 기다리므로
실험 취소/예산 종료가 장시간 지연될 수 있다. 고유 network만 정리한다는 소유권 경계는 유지되지만,
시간 상한은 유지되지 않는다.

**보완 방향:** 전체 cleanup 예산/종료 정책을 명시하고, 이미 정리된 marker를 구분하며,
지연·실패·미완료 정리 상태를 증거로 남겨야 한다. Docker 지연을 모의하는 adapter 종료 경로 검증이 필요하다.

### Minor M1 — output token만 보고된 API 오류 종료가 `unreported`로 기록된다

**위치:** `examples/ace-rtl/native_worker.py:30`.

API 오류 분기의 usage 판정은 `input_tokens`만 확인한다. 이전 성공 응답에 `completion_tokens`만 있고
이후 요청이 실패하면, sidecar에는 실제 `output_tokens`가 있는데도 `usage_status="unreported"`가 된다.
정상 bridge·adapter의 판정은 input/output 양쪽을 검사하므로 종료 경로에 따라 의미가 달라진다.
brief §6의 null/partial 계약에 맞춰 동일한 판정식을 사용해야 한다.

### Minor M2 — readiness·준비 실패는 native sidecar와 개별 진단 근거 없이 반환된다

**위치:** `examples/ace-rtl/native_adapter.py:125–128, 143–152`.

wrong pin/누락 asset/wrong interpreter/필수 dependency 실패는 구체적인 `ready['checks']`가 있어도
일반 detail만 반환하며 `native-execution.json`을 만들지 않는다. 준비 중 timeout·unsupported 조기 반환도
sidecar 생성보다 앞선다. 보고서의 현재 `yaml` 누락 상태가 바로 이 경로다.
실패 자체는 명시적이지만 G/F 소비자가 source 문제와 interpreter 문제를 실행 증거로 구별하기 어렵다.
실행 전 차단의 sidecar 정책과, 확인 불가능한 provenance의 null 처리·진단 보존을 명시할 필요가 있다.

## 중점 항목별 명세·실행 경로 판정

| 항목 | 판정 및 근거 |
|---|---|
| 실제 pinned loop·반복 보존 | 충족. `native_bridge.py:260–262`가 후보 snapshot에서 import한 실제 `cli.run_attempt`를 호출한다. upstream `cli.py:131–348`이 iteration·평가·reflector·coordinator·fresh-start를 소유한다. processor/출력/client 경계는 bridge가 교체하므로 원본 전체 CLI·native harness의 실행과는 구별된다. |
| 세 역할 제품 client | 충족. Generator는 `transport.call`; Reflector/Coordinator는 동일 `LLMClient.call_llm` 치환을 통해 `ModelSettings.from_env`·`models.complete`를 소비한다(`native_bridge.py:143, 164–176, 186`). RuleAdvisor의 추가 요청도 동일 client를 거쳐 reflector로 기록된다. Coordinator가 12번째 실패에서 API를 호출하는 upstream 정책과 테스트의 13번째 fresh-start 경로를 대조했다. |
| private/evaluator context | 검토한 호출 경로에서 누출 결함 없음. public row는 harness/reference를 제거하고, reflector context·coordinator immutable helper·evaluator report는 차단/안전 집계로 교체한다(`native_cvdp.py:77–81`, `native_bridge.py:128–133, 166, 249–256`). inner evaluator에는 private row를 전달하지만 그 feedback/content/path를 모델 prompt로 전달하지 않는다. 임의 Python 후보는 명시된 trusted plugin 계약이며 OS sandbox라는 주장은 하지 않는다. |
| active candidate prompt/code | 충족. `RoleTransport`가 후보의 guidance를 읽고 후보 Python을 compile/exec하여 모든 실제 요청에 실행한다(`native_bridge.py:57–72, 80–84`). CandidateStore A/B 테스트는 모델 request 차이·imported code 차이·candidate hash를 검사한다. 단순 파일 변경 검사에 그치지 않는다. |
| 공식 inner/outer 평가 | C 경계 충족. `NativeCVDPEvaluator`는 실제 기존 CVDP subprocess 평가와 raw 결과를 사용한다. native 실패라도 유효한 제출물을 가진 정상 worker 종료는 `completed`여서 기존 `GroupRunner.trial`의 outer 평가로 이어진다. inner pass를 최종 성적으로 쓰지 않는다. outer count/time producer 연결은 F 인계다. |
| CID 실제 row 기반 지원/차단 | 정적 지원 근거 있음. 고정 hash의 실제 row를 대상으로 input/context·모든 output target을 추출한다. cid002/004/016과 cid007 lint의 실제 row·multi-file 테스트가 있고, cid007의 상용 helper·PNR/합성 자산은 구체적 gate로 제외한다. 보고된 197 eligible/27 exclusion은 실도구 성공이 아니며 별도 live 검증이 필요하다고 정확히 표시했다. |
| 제출 경계 | 검토 경로에서 충족. 모든 선언 section·누락/중복/미선언/빈 출력/Markdown·target 경로를 검사하고 파일 읽기/쓰기에는 symlink 거부 `safe_path`를 사용한다. |
| sidecar truth·사용량 | 부분 충족. 정상 종료에는 역할별 실제 요청·부분 usage·inner 평가·raw evidence·surface hash를 남기고 전체 비용/token은 null이다. I1/M1/M2 때문에 실패 종료 증거는 완전하지 않다. |
| timeout·cleanup | 부분 충족. 독립 worker process group·관측 descendant·고유 evaluator network 정리 경로는 존재한다. I2의 종료 시간 상한 결함이 남는다. 실제 Docker cleanup 성공은 보고서에서도 모의/미검증으로 구분한다. |
| 기존 coding profile | 범위 준수. 기존 profile/adapter를 수정하거나 이름만 바꾸지 않고 별도 native 파일을 추가했다. 기존 회귀 통과는 보고된 테스트 결과에 한정한다. |

## C adapter 자체 실행 가능성·인계

**정적 연결 기준으로 C adapter의 실행 경로는 성립한다.** F의 registry/CLI/loader 없이도
직접 `ACENative(config).run(RunRequest)`를 호출하면 독립 `native_worker.py`가 public descriptor를
pinned row와 대조하고 후보 native loop를 실행한다. worker→bridge→기존 evaluator/client의 sibling/import
연결에 별도의 F 구현을 요구하는 호출 단절은 발견하지 못했다.

다만 **현재 환경에서 live 실행 가능/성공 판정은 아니다.** 보고된 interpreter readiness는 `yaml` 누락으로
false이며, worker fixture는 YAML import stub·모델 응답 모의·evaluator 모의를 사용한다. 실제 제품 client와
공식 evaluator를 동시에 사용하는 native E2E는 `not_run`이다. 준비된 Python 의존성·모델 환경·공식 CVDP
평가 자산이 필요하고, F의 최종 연결을 완료해도 I1/I2는 C 코드에 남는다.

F의 native profile allow-list/registry/배포 fingerprint/outer sidecar producer 인계는 구체적이며,
이는 C 범위 미구현으로 세지 않았다. C의 승인 전에는 I1/I2를 보완하고 실패 요청 보존·지연 cleanup 경로를
검증해야 한다. M1/M2도 sidecar 소비 계약 확정 시 함께 정리하는 것이 적절하다.

## 수정 라운드 1 — 개발 보완·실제 회귀 결과

2026-10-01, 기준 `4fd8af1d8864c21f14a3e7f06508bba412ce99e7`.
위 최초 리뷰와 그 검증 수준은 당시 기록으로 보존한다. 이번에는 C 소유 코드와 새 native
테스트를 수정하고 실행했다. **I1·I2·M1·M2 보완 완료**이며 독립 재리뷰 승인 선언은 아니다.

| finding | 수정·검증 |
|---|---|
| I1 | `native_artifacts.finalize`를 worker 정상/API/일반 예외 및 adapter 종료에 공통 적용했다. 실제 journal을 대체 병합해 중복 없이 요청 status/duration/token을 보존한다. Markdown output 거부·evaluator 예외·이후 API 실패의 실제 worker main→adapter 경로에서 요청 누락을 재현한 후 회귀 통과 |
| I2 | adapter outer 예산에서 `min(1초, 전체의 10%)`를 정리용으로 예약한다. process 진단/wait와 모든 network 명령은 하나의 outer deadline을 공유한다. native inner evaluator에도 동일 예약 정책과 bounded cleanup 적용. 완료 marker는 재정리하지 않고 timeout/incomplete/deferred를 journal·sidecar에 기록. 6개 marker(3개 완료)를 두고 Docker 요청 지연을 모의하여 0.4초 outer 예산에서 반환 0.7초 미만·Docker 호출 1회·완료 marker 미호출·후속 deferred 확인 |
| M1 | usage 계산에서 input/output 양쪽을 검사한다. output token 9·input null 응답 이후 API 오류도 `partial` 유지. 미수집 token/cost는 null이고 전체 사용량으로 합산하지 않음 |
| M2 | 준비 시작부터 version 1 sidecar를 만든다. readiness 개별 checks, 안전한 diagnostic/error_type, timeout/unsupported 상태를 기록한다. 확인하지 못한 source revision/hash·candidate hash·task ID는 null. wrong pin+누락 interpreter 및 PNR unsupported 조기 종료에 요청을 꾸며 넣지 않는 회귀 통과 |

새 `native_artifacts.py`·`native_cleanup.py`는 F의 예제 배포 및 dependency fingerprint에
포함해야 한다. schema version은 1 유지하며 `readiness_checks`, `diagnostic`, `cleanup`은 additive다.
정리 실패는 숨기지 않는다. 남은 owned network marker가 `incomplete/deferred`이면 실제 Docker
자원 정리가 끝났다는 뜻이 아니며, 예산 뒤 동기 재시도/별도 iteration별 15초 대기는 하지 않는다.
단독 `run_worker`의 테스트용 기본 종료 예산은 실행 deadline 뒤 고정 0.3초이며,
제품 adapter는 이를 사용하지 않고 원래 outer deadline을 명시한다.

### 실제 covering test 명령

CWD: `/Users/wt.jeong/workspace/agent-optimizer/.worktrees/final-mvp-c-20261001`.

```bash
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests TMPDIR=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/tmp AGENT_OPT_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home XDG_CACHE_HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/cache /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m unittest test_native_ace test_native_cvdp -q
```

최종 `Ran 28 tests in 4.788s`, `OK`, 종료 코드 0, skip 없음.
새 5개 회귀는 worker 예외 journal/usage, 전체 cleanup deadline/완료 marker,
readiness nullable provenance, unsupported sidecar, owned cleanup argv·stderr 비노출을 검사한다.
기존 실제 process timeout/cancel·독립 worker·private sentinel·pinned native loop/row 회귀도 실행했다.
모델·evaluator·Docker 호출은 모의이고 OS child 종료 테스트는 실제 공유 Python process다.

```bash
HOME=/var/folders/s0/kkh09qs52bv52h5n4nf4d2fw0000gq/T/opencode/final-mvp-c/session-20261001/home PYTHONDONTWRITEBYTECODE=1 /Users/wt.jeong/workspace/agent-optimizer/.venv/bin/python -m ruff check . --no-cache
```

`All checks passed!`, 종료 코드 0. 이번 라운드에서 전체/기존 coding 테스트 묶음은 재실행하지 않았다.
실모델·실 Docker cleanup·실시뮬레이터는 `not_run`. 설치/다운로드/하위 에이전트/기본 repo 수정/push 없음.
요청 metadata에는 허용된 request 필드만 병합하고 provider/evaluator 오류 원문·prompt·private 자료·키·Docker stderr를 복제하지 않았다.
