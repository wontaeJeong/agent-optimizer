# 모델 설정과 앱 실행 경로 단순화 설계

## 목표와 확인된 문제

설치형 앱의 실제 ACE-RTL 스킬 프로필 + 공식 CVDP 실행은 `agent-opt tui`의 3번 선택 또는
`agent-opt init --profile ace-rtl --workspace PATH` → `agent-opt prepare PATH/experiment.toml` →
`agent-opt run PATH/experiment.toml`이다. 저장소에서 바로 실행할 때도 준비된
`examples/ace-rtl/experiment.toml`을 `agent-opt run`으로 선택할 수 있다. 개발용
`sh scripts/bootstrap.sh doctor --model` → `make live ARGS="--iterations 1"`을 사용자 필수 E2E
명령으로 안내한 것은 잘못이다. 1회 반복은 검증 시간을 줄인 개발 실험이며 앱의 기본 ACE 실험은
설정대로 3회 수정한다. 실제 모델·Agent·공식 평가를 실행해야 E2E 완료라고 말할 수 있다.

설정에는 `AGENT_OPT_MODEL_BASE_URL`과 `AGENT_OPT_MODEL_ENDPOINT`의 배타적 분기,
개발 메뉴의 URL 방식 선택, 같은 구현을 부르는 `agent-opt validate`/`agent-opt plan`,
같은 argv를 만드는 `init --command-json`/`--command`, 인수 없는 `agent-opt doctor`의
준비 상태와 무관한 바이너리 나열이 있다. 사용자 명령·모델 환경·개발 진단을 전체 점검하고
이처럼 **실제로 중복되거나 오해를 만드는 선택**을 정리한다. 데이터셋·평가기·Optimizer 선택,
일반 OpenCode 하네스의 독립 `AGENT_OPT_MODEL` 선택자, 연구별 서로 다른 editable 대상과
독립적인 개발용 도구·공식 평가 smoke는 각각 고유 역할이 있으므로 유지한다.

## 설정 계약

- 모델 HTTP 설정은 `AGENT_OPT_MODEL_BASE_URL`(예: `https://host/v1`),
  `AGENT_OPT_MODEL_API_KEY`, 선택적 `AGENT_OPT_MODEL_ID`만 받는다. URL 끝의 `/`는 정리하고
  요청은 `{BASE_URL}/chat/completions`로 보낸다. 표준 경로가 아닌 서버는 이 프로필의
  지원 범위에서 제외한다. 기존 HTTPS/loopback HTTP 및 URL 자격증명·query·fragment 금지를 유지한다.
- `AGENT_OPT_MODEL_ENDPOINT`를 비어 있지 않게 제공하면 무시하거나 자동 전환하지 않고
  `AGENT_OPT_MODEL_BASE_URL`로 이전하라는 오류를 반환한다. 두 값을 동시에 주더라도 같다.
  코드·메뉴·예제·컨테이너 전달 목록·CI·현행 사용자/개발 문서에서 이중 URL 선택을 제거한다.
  과거 실행 증거와 역사적 설계 문서는 당시 기록으로 유지한다.
- 앱은 임의 `.env` 파일을 자동 탐색하거나 자격증명을 저장하지 않는다. 비대화형 CLI는
  환경/credential store에서 받고, 개발자가 `.env`를 쓴다면 셸에서 내보낸다. TUI는
  필수 모델 값이 없을 때만 현재 실행 세션에 한정해 URL·모델 ID·숨김 토큰을 묻는다.
  유효한 기존 값을 재사용하고 토큰을 출력·실험 설정·보고서에 남기지 않는다. 취소·잘못된
  입력에서는 모델 호출이나 실험 실행을 시작하지 않는다. 모델 연결 실패는 명시적으로 실패한다.

## 앱과 개발 진입점

- 대화형: `agent-opt tui` → ACE-RTL + CVDP 예제 직접 선택 → 작업공간·준비 확인 →
  고정 자산 준비 → 필요한 모델 값의 세션 입력 → 정적 계획 확인 → 실행 확인 →
  실제 Agent/공식 CVDP 평가 → 보고서. 기존 ACE 실험을 선택하는 경로에서도 같은
  세션 입력을 제공한다. 일반 연구 Optimizer에 필요한 API 설정과 OpenCode 하네스에
  선언된 모델 선택자도 부족한 값만 물으며 모델 없는 실험에는 모델 입력을 요구하지
  않는다. 정적 진단에 `model.configuration`이 포함된 실험에서는 모델 입력 이후에
  진단하므로 입력 부족으로 실행 확인 전에 잘못 차단되지 않는다. 모델 API의 필요성은
  연구 stage 또는 전용 하네스의 선언된 환경 전달 값으로 판정하며, 실행 승인 전에
  하네스 플러그인 구현 파일을 import하지 않는다. 일반 OpenCode의 선택형 호환 API
  환경 전달만으로 별도 API 키를 강제하지 않는다.
- 비대화형: `agent-opt init --profile ace-rtl --workspace PATH` → `agent-opt prepare
  PATH/experiment.toml` → `agent-opt run PATH/experiment.toml`. 저장소 개발자는
  `make setup-core` 뒤 `agent-opt run examples/ace-rtl/experiment.toml`을 사용할 수 있으나
  ACE 자산은 별도로 준비돼 있어야 한다. `doctor --plan PATH`는 선택적인 정적 진단,
  `doctor --plan PATH --model`은 명시적인 모델 호스트 호출이다. 둘 다 run이나 공식
  평가의 완료를 대신하지 않는다. `run`의 예제 lifecycle 검증·실패 전파는 유지한다.
- 중복 공개 명령 `validate`는 없애고 `plan`을 남긴다. `init --command-json`은 없애고
  `--command`의 인용 가능한 문자열을 argv로 분해한다. wizard가 내부 argv를 만들 때에도
  안전하게 한 번 직렬화·역직렬화하며 실제 실행은 argv 배열·`shell=False`를 유지한다.
  인수 없는 `agent-opt doctor`는 바이너리 목록 대신 `--plan` 또는 `--dataset`을 안내하는
  사용 오류로 바꾼다. `doctor --plan`/`--dataset`, `datasets list/prepare`, `run-session`,
  `report` 등 고유 기능은 유지한다.
- `make setup-core`·`make doctor-core`·`make smoke`와 개발용 `doctor --model`/`live`는
  개발자/실도구 분리 검증에 남긴다. 사용자 빠른 시작과 도움말은 앱 명령을 앞세우고,
  개발 문서에만 추가적인 호스트 API/컨테이너 도구 probe·1회 비용 제한 실행을 설명한다.

## 구현 경계와 검증

기존 `ModelSettings`, CLI/TUI의 `collect_plan`/`_launch_existing`, ACE 예제의
`lifecycle.run`·`ACEOpenCode.launch_existing`, 개발 메뉴와 문서의 표현을 수정한다.
ACE/CVDP 준비·공식 평가·스냅샷·split/평가 분리 계약, 모델 credential의 컨테이너 전달
경계는 유지한다. 공통 코어에 ACE 전용 다운로드·평가 분기를 새로 넣지 않는다.

회귀 검사는 BASE_URL의 표준 경로·URL 오류·기존 ENDPOINT 명시 거부·키 비노출,
TUI의 준비/실행 확인·키 숨김·세션 범위·실패 전파, 비대화형 앱 경로와
`--command` 인용/실제 argv, 제거한 공개 옵션·중복 명령의 거부를 확인한다.
변경 전 기준은 `make setup-core`와 `make test` 628개(15 skip) 통과다.
변경 후 관련 테스트·전체 테스트·lint·합성 실행·설치 wheel 경로와 가능한 Docker/CVDP
검사를 실행한다. 자격증명과 외부 자산이 없으면 실모델 E2E 미실행을 명시하고 성공으로
대체하지 않는다. CLI/TUI UX 변경 전·후 캡처와 재현 방법을 PR 본문에 넣는다.
