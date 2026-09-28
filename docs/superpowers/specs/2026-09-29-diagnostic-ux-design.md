# setup·doctor 진단 UX 설계

## 목표와 조사 결과

`setup`, `doctor`, dataset/ACE 자산 준비가 실패하면 사용자가 터미널만 보고 실패 단계·원인·수정 방법·재실행 명령을 결정할 수 있어야 한다. 기존 모듈 흐름을 유지하고 별도 로깅/관측 시스템은 만들지 않는다.

현재 `readiness.Runner.run()`은 subprocess 실패를 `None`으로 축약해 exit code, timeout, 실행 오류, stderr를 잃는다. `diagnostics.collect_checks()`와 plan/dataset collector는 이 정보를 보존하지 않으며 일부 예외를 일반 문구로 바꾼다. ACE setup은 로그 파일 경로는 알리지만 `_run()` 실패 시 원인은 일반 오류로 축약한다. `bootstrap.sh`도 uv installer/sync 출력은 로그에만 남기고 사람용 stderr에는 원인 분류가 없다. `scripts/dev.py`는 setup 실패를 JSON `blocked` 객체로 끝내고, TUI readiness 실패는 일부 경로에서 check ID·구체 원인을 보여주지 않는다.

기준은 `origin/main`의 `c6a4bd4`이다. 코어 환경을 준비한 후 전체 테스트 885개가 통과했고 79개가 skip, Ruff가 통과했다. 첫 시도에서 나타난 15개 오류는 새 워크트리에 `.venv`가 없어서 생긴 환경 오류였으며 `make setup-core` 이후 해소됐다.

## 출력 계약

- doctor check JSON의 기존 필드 `id`, `area`, `status`, `message`, `remedy`와 report 구조·종료 코드를 유지한다. public `cause`/`retry` 필드는 추가하지 않는다.
- 실패한 `message` 문자열에는 선택적인 `Cause:` 또는 `Blocked by:` 줄을, `remedy` 문자열에는 선택적인 `Retry:` 줄을 담는다. 정상 check 문자열은 바꾸지 않는다. 공통 human renderer는 이 표식을 해석해 `[error] id: ...`, `Cause`, `Blocked by`, `Fix`, `Retry`를 별도 줄로 표시한다. JSON은 동일한 키와 문자열 타입을 유지하고 안전하게 정제된 진단만 포함한다.
- 일반 개발 `setup`은 사람용 진행·완료·실패 출력을 사용한다. 실패 출력은 `[setup] <stage>: failed`, `Cause`, `Log`(존재 시), `Fix`, `Retry`를 포함한다. `setup`에는 machine-readable 옵션이 없으므로 JSON 결과를 섞지 않는다. 기계 자동화용 doctor 출력은 기존 `doctor --json`으로 한정하며 stdout에 JSON 문서 하나만 쓴다.
- setup 로그 파일은 계속 보존한다. 터미널에는 안전하게 분류·정제한 최대 1~3개의 의미 있는 요약만 보여주며 원문 tail/dump는 하지 않는다.

## 내부 결과와 안전한 원인 요약

`Runner.run()`은 내부 전용 subprocess 결과 객체를 반환한다. 실행 결과에는 성공 여부, return code, timeout, 예외 종류, stdout/stderr, 안전한 명령 label 및 elapsed time을 보존한다. 이 객체를 public JSON이나 화면에 직접 직렬화하지 않는다.

작은 공통 진단 helper가 실패 종류를 다음 우선순위로 분류한다: 실행 파일 없음, timeout, permission denied, Docker daemon/socket 접근, TLS/certificate, DNS/connection, non-zero exit, offline cache miss/file missing, lock/platform/config mismatch, unknown. 비정상 종료에서는 가능하면 exit code와 정제된 1~3줄을 붙인다. Docker·Git·uv·Python command별 검사와 dataset/ACE setup은 같은 helper를 사용하고, 예외를 일반 문구로 치환하는 기존 broad catch에는 safe cause를 전달한다.

정제 규칙은 다음과 같다.

- KEY/TOKEN/SECRET/PASSWORD/AUTH/CREDENTIAL 및 model credential 설정에 해당하는 환경변수 값은 출력 후보에서 제거한다.
- proxy URL의 userinfo, Bearer/API key/token 형식, `AGENT_OPT_CA_BUNDLE` 및 관련 CA 환경변수의 사용자 경로를 제거한다.
- stdout/stderr 전체는 절대 출력하지 않는다. 로그에서 의미 있는 오류 행만 선택하고 위 정제 규칙, 길이 제한, 최대 행 수를 적용한다.
- Python 준비 전의 `bootstrap.sh`에서는 allow-list 분류만 수행한다. 신뢰할 수 없는 로그 행을 raw 출력하지 않고 사전 정의된 TLS/DNS/permission/cache/unknown 원인만 보여준다.
- 저장되는 ACE `doctor.json` 진단 결과도 raw subprocess stdout/stderr를 포함하지 않는다.

## 구성별 동작

### Readiness와 doctor

`Runner.probe()`는 내부 command outcome으로 `status/message/remedy`를 구성한다. 실패 원인이 있으면 기존 `message`에 `Cause:`를 포함하고, retry command가 안전하고 명확할 때 기존 `remedy`에 `Retry:`를 포함한다. 선행 검사 실패는 `blocked`로 남기고 실패 dependency ID를 `Blocked by:`로 표시한다. 독립 검사는 계속 수집한다.

`readiness._dataset()`, `collect_plan()`, `_ace_asset_check()` 및 ACE `diagnostics.collect_checks()`는 알려진 안전한 예외 원인을 보존한다. 실패 원인이 없거나 민감값 제거 후 정보가 남지 않는 경우에는 원인 분류만 제공한다. `doctor`는 read-only, project 파일 비변경, bytecode 미생성, 독립 오류 aggregation, 일반 경로 모델 API 미호출, `--model` 전용 probe, Docker pull/build 금지, 기존 임시 container 소유권/cleanup 안전성을 유지한다.

### Setup과 bootstrap

ACE setup의 `_run()`은 현재 로그 구조를 유지하면서 실패 시 해당 log를 요약한다. clone/checkout, driver venv/pip sync, Docker build, image inspect, simulator/OpenCode verification, dataset download/cache, Python validation, final doctor가 실패한 위치와 안전한 cause를 상위 `scripts/dev.py`까지 전달한다. 재시도 없이 실패 단계, 해결 안내 및 동일 범위 setup 명령을 제시한다.

`bootstrap.sh`는 Python/uv 환경이 아직 없을 수 있으므로 installer/download/sync 로그를 POSIX allow-list로 분류한다. uv sync 실패 시 선택된 `--core`/`--dataset` 범위와 offline 여부를 유지한 Fix/Retry를 출력한다. Docker prerequisite 확인은 기존 aggregate 동작을 유지하면서 daemon/socket 원인을 안전하게 분류한다.

`scripts/dev.py`는 setup 예외를 사람용 진단으로 출력하고, stage·log·복구·재실행 정보를 유지한다. 실패 시 `{"status":"blocked", ...}`를 출력하지 않는다. dataset setup, full/core setup, final doctor와 demo 실패 모두 동일한 human output 계약을 따른다. doctor `--json`은 현재 stdout 단일-document 동작을 유지한다.

### CLI/TUI

CLI와 개발 doctor는 기존 check renderer를 재사용해 원인과 retry를 별도 줄로 출력한다. TUI의 readiness 실패는 실패한 모든 check ID 및 각 Cause/Blocked by/Fix/Retry를 표시하며 실행을 시작하지 않는다. 출력 계층은 수집한 원인을 generic `configuration/assets/model` 안내로 다시 축약하지 않는다.

## 검증 조건

실패 유형별 단위 테스트와 실제 출력 검증을 추가한다: command missing, non-zero, timeout, permission, Docker socket, TLS, uv sync, Docker build, dataset download/cache, blocked dependency, setup log 요약, API key/token/SECRET/proxy userinfo/CA 경로 및 timeout output 비노출. JSON 단일 문서·secret-free·기존 필드, setup human output, TUI check 식별, doctor aggregation/read-only/no-bytecode/model probe/컨테이너 정리를 회귀 테스트한다.

가짜 subprocess 결과로 Docker daemon permission, TLS가 포함된 Docker build, dataset download/cache 실패의 before/after 터미널 출력을 비교한다. 전체 unittest, Ruff, 코어 doctor 및 합성 demo를 실행하고 실제 Docker/model/network 통합은 수행하지 않았다고 구분한다.
