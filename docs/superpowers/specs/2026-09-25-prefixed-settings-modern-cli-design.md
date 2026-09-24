# 접두어 설정·현대적 CLI 설계

## 목표와 결정

프로젝트 소유 환경변수는 `AGENT_OPT_`로 통일합니다. 설정 입력에 Pydantic Settings,
공개 CLI 파싱에 Typer, 터미널 진행 표시에 Rich를 적용합니다. 접두어 없는 `MODEL_*`는
즉시 중단하며 별칭·대체 입력·유예 기간은 없습니다. `agent-opt init`의 argv 입력
형식 변경은 허용합니다.

## 환경변수 경계

`MODEL_ENDPOINT`, `MODEL_BASE_URL`, `MODEL_ID`, `MODEL_API_KEY`는 각각
`AGENT_OPT_MODEL_ENDPOINT`, `AGENT_OPT_MODEL_BASE_URL`, `AGENT_OPT_MODEL_ID`,
`AGENT_OPT_MODEL_API_KEY`로 바꿉니다. `AGENT_OPT_MODEL`은 OpenCode 모델 선택자,
`AGENT_OPT_CA_BUNDLE`은 선택적 CA 설정으로 유지합니다. 예제 전용 `CVDP_PYTHON`도
`AGENT_OPT_CVDP_PYTHON`으로 바꿉니다. 소비자·진단·메뉴·예제·컨테이너 전달 목록·테스트·
`.env.example`·현재 안내를 함께 갱신하되 과거 검증 기록은 소급 수정하지 않습니다.

외부 프로그램이 정의한 이름은 유지합니다. `OSS_SIM_IMAGE`는 고정 CVDP driver의
Dockerfile/Compose 인터페이스이고, `OPENCODE_CONFIG`·`OPENROUTER_API_KEY`는 provider
인터페이스입니다. proxy·TLS·`DOCKER_DEFAULT_PLATFORM`·`UV_*`·`PATH`·`PYTHONPATH`도
외부 계약입니다. 기존 명시적 범위에서만 전달하며 인증정보를 결과나 Agent 파일에 복사하지 않습니다.

## 설정과 런타임 구성

Pydantic Settings는 모델 환경 입력에만 사용하고 `.env`는 자동으로 읽지 않습니다. endpoint와
base URL의 배타 선택, HTTPS 또는 loopback HTTP 제한, 모델 ID 검증, 인증 누락 오류,
repr·진단·오류·보고서에서 키 비노출을 유지합니다. 메뉴·테스트·doctor가 명시적으로 넘긴
환경 mapping은 프로세스 환경으로 대체하지 않습니다. 단기 요청 worker에는 검증된
endpoint/모델/키를 전달하며 전체 timeout과 `shell=False`를 유지합니다. 설치 전에도
개발 진단이 모델 모듈을 import하므로 Pydantic은 실제 모델 설정을 검사할 때만 로드합니다.
패키지 미설치 시 코어 help/doctor는 시작하고 모델 전용 검사만 의존성 누락으로 보고합니다.
기존 TOML/JSON 실험 계약과 소스·평가 격리는 유지하며 전체 schema는 전환하지 않습니다.

## CLI와 터미널 흐름

`agent-opt`의 argparse 명령 파싱을 Typer로 바꾸되 registry·준비·검증·runner·보고서·doctor
실행 로직은 재사용합니다. 명령 이름, JSON 결과 구조, 의미 있는 실패 코드, 읽기 전용 doctor,
TUI의 공통 `init` 경로를 유지합니다. `init`의 표준 argv 입력은
`--command-json '["python", "agent.py", "--input", "{task_dir}"]'`으로 정하고
모호한 다중 토큰 `--argv`를 제거합니다. 설치 전에도 setup/help/doctor가 동작하도록
bootstrap과 `scripts/dev.py`는 표준 라이브러리 진입점으로 둡니다. 팀 컴포넌트는
CLI 선택지나 설치 entry point 대신 registry에서 탐색합니다.

Rich는 대화형 stderr의 진행·준비 표시에 사용합니다. 데이터셋·stage·task·phase·iteration·
경과 시간·trial 예산·느린 과제 정보를 유지합니다. 비대화형 로그에는 제어 문자를 내보내지
않고 JSON stdout은 단일 문서로 유지합니다. 일반 진단 JSON과 저장된 보고서의 전역 출력은
바꾸지 않습니다. 표시 오류 때문에 실험 오류가 성공으로 바뀌어서는 안 됩니다.

## 의존성과 검증

`pydantic-settings`·`typer`·`rich`의 호환 버전을 런타임 의존성에 추가하고 frozen 설치용
`uv.lock`을 갱신합니다. Python >=3.11, 코어 setup/offline 경로를 유지합니다. benchmark
소스·CVDP driver 의존성·Docker 이미지·모델 provider 버전·채점 규칙은 변경하지 않습니다.

접두어 전용 설정, 명시적 mapping 격리, 키 비노출, 진단·메뉴·컨테이너 전달, Typer 명령·
종료 코드, JSON argv, 읽기 전용 doctor, TTY/비TTY stderr와 JSON 분리를 테스트합니다.
기존 변수명을 쓰는 테스트도 갱신합니다. 관련 테스트·전체 unittest·Ruff·모델 없는 최소
데모·frozen 설치·빌드·diff를 확인합니다. 실제 provider 호출이나 benchmark 채점 성공은
이 정리의 검증 결과로 주장하지 않습니다.
