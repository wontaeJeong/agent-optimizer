# Python native ACE·CVDP 연결

기존 `source.toml`·`harness.toml`·`harness-claude.toml`은 coding 프로필이다.
별도 native Agent ID는 `ace-rtl-native`, adapter ID는 `ace_native`, profile ID는
`ace-native`다. 코어 catalog/registry/CLI 등록은 F가 연결한다.
현재 core harness profile allow-list의 `native`·`compatibility` 허용/검증도 F/G 연결 대상이다.
Agent source manifest는 기존 loader 계약 그대로 사용한다.

## 준비 API

`native_prepare.prepare_source(upstream, destination)`은 이미 확보한
`fead921f18bb57345b5a41ef93ba625be208e99c` Git tree를 읽기 전용으로 export한다.
fetch·설치·동기화는 하지 않으며 destination은 upstream 밖의 새 디렉터리여야 한다.
반환 `path`로 `source-native.toml`의 local source를 작성한다.

`native_prepare.prepare_dataset(dataset, output, *, cids, splits=None)`은 고정 HF 파일의
SHA-256을 확인하고 사용자가 선택한 CID만 준비한다. public `native-task.json`에는
input과 빈 output target만 들어간다. private harness는 benchmark의 `evaluation`에만
남는다. split을 지정하지 않으면 전부 validation이며, 실행 writer가 명시적으로
train/validation/test와 family 분리를 구성해야 한다. 자동 held-out 분할이 아니다.

`native_prepare.readiness(source, python)`은 소스 pin/asset hash·Python 3.12·
`yaml`/`pydantic_settings`를 검사한다. 디렉터리·모델 요청·다운로드를 만들지 않는다.
공식 CVDP driver/repo/이미지 준비와 모델 환경 확인은 별도 기존 준비/진단 경계를
사용해야 한다. engine ready가 live 실행 성공이나 평가 환경 ready를 뜻하지 않는다.

## 실행 API

- `native_adapter.ACENative(config=None).run(RunRequest) -> ExecutionResult`
- `native_evaluator.NativeCVDPEvaluator(config=None).evaluate(Task, output_dir, timeout_seconds) -> Evaluation`
- trusted fixture/연동 검증: `native_bridge.run_native(request, row, *, evaluator=None, settings=None, completion=complete)`

adapter config 또는 profile `[native]`에는 `python`, 고정 원본 `dataset` 절대경로,
`max_iterations`(기본 3, 1~30), `llm_timeout`(기본 60초), `evaluator_timeout`(기본 120초),
`evaluator`(기존 CVDP의 repo/python/sim_image/sim_image_id)가 들어간다.
단일 outer trial에 attempt 1개를 수행하고 전체 상한은 `RunRequest.timeout_seconds`다.
inner 예산이 outer 잔여 예산보다 작게 제한된다. 상용 도구 어댑터는 없다.

세 역할은 모두 기존 `ModelSettings.from_env`·`models.complete`를 사용한다.
`AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`, `AGENT_OPT_MODEL_API_KEY`가 동일하며
coding provider selector `AGENT_OPT_MODEL`은 native 필수값이 아니다. 키는 환경에만
있고 provider fallback·추가 retry는 하지 않는다. Coordinator는 upstream 보수 정책에
따라 매 iteration마다 API를 호출하지 않는다(12번째 실패 후 실제 모델 분기 검증).

## 실행 경계

후보 snapshot에서 원본 `ace_cvdp_native.cli.run_attempt`·FocusedDebugger·
FreshStartCoordinator를 import하고 그대로 반복 루프를 실행한다. 원본 전체 CLI의
다중 datapoint/attempt 기본값은 사용하지 않는다. public-only processor와 안전한
AceIterationModel 출력 처리만 trusted bridge에서 연결한다. 실제 공식 평가는
기존 CVDP evaluator subprocess를 사용한다. upstream native harness patch는 이 경로에서
실행하지 않으며, private checker/`.env`/로그를 읽는 context·feedback helper를 차단한다.
내부 feedback은 공식 결과의 binary 상태/집계만 허용한다.

GEPA editable은 `native/guidance.md`, Meta-Harness editable은 실제 import·실행되는
`native/orchestration.py`다. upstream 및 trusted bridge/evaluator는 editable 밖이다.
임의 Python 후보의 실행은 OS 보안 sandbox가 아니며 기존 trusted plugin 계약을 따른다.

native inner pass는 최종 점수가 아니다. 정상 종료 뒤 GroupRunner의 기존 outer trusted
evaluator가 제출 target을 다시 판정한다. infra/API 오류는 성적 0으로 가장하지 않는다.
다중 target은 전부 제출해야 하며 누락·중복·미선언·빈 출력·traversal·symlink를 거부한다.

## 증거

`RunRequest.logs/native-execution.json`은 P0 schema version 1 sidecar다.
중첩 JSON은 `ExecutionResult.metrics`에 넣지 않는다. 역할별 실제 요청만 기록하며
미제공 token/cost는 null, 전체 usage는 `partial` 또는 `unreported`다.
attempt/iteration·inner evaluation wall time·outer 평가 owner를 별도로 기록한다.
outer 평가 횟수/시간은 C가 수집하지 않아 null이며 F producer가 기존 최종 평가 자료로
연결한다. raw prompt/RTL/private 내용/키는 sidecar에 넣지 않는다.

timeout·취소·예외에는 native process group과 관측한 descendant를 종료·수거한다.
공식 evaluator가 새 process session을 만들더라도 descendant 목록으로 정리하며,
평가 직전 기록한 고유 Docker network ID로 해당 network의 container만 정리한다.
`native-progress.json`·`native-requests.json`으로 중단 전 iteration/요청을 보존한다.
raw 자료는 보고서 서버 공개 asset에 포함하면 안 된다.

실패 종료에도 `native_artifacts.py`가 요청/진행 journal을 복구한다. input 또는 output token만
있어도 partial이며 미제공 값은 null이다. 준비 차단도 sidecar를 남기고 검증하지 못한 provenance는
null, 개별 readiness 진단은 `readiness_checks`로 기록한다.
`native_cleanup.py`의 모든 정리 명령은 공통 deadline의 잔여 시간 이하(개별 최대 1초)로 제한된다.
outer/inner 예산의 `min(1초, 10%)`를 정리에 예약하며 완료 marker는 재정리하지 않는다.
미완료/예산 부족은 `cleanup`·owned marker에 `incomplete/deferred`로 남긴다.

검증 범위·CID별 실제 row 판정·정확한 명령은
`docs/verification/final-mvp-c-20261001.md`를 따른다. fixture 성공은 live 성능 증거가 아니다.
