# 개발환경 온보딩 설계

## 목표와 승인 범위

새 개발자가 한 명령으로 개발환경을 준비하고, 설치 전후의 문제와 해결 방법을
`doctor`에서 확인할 수 있게 한다. Mac 및 Ubuntu를 대상으로 기존 Python 개발 도구를
확장하고 Makefile을 공통 진입점으로 둔다. 기본 명령은 전체 예제 환경을 준비한다.

사용자가 승인한 설치 경계:

- Git 및 Docker Engine/Compose는 사전 설치 대상으로 진단하고 OS별 설치 안내를 제공한다.
- uv, Python 3.12, 프로젝트 개발 의존성, 고정 외부 소스·데이터, 평가·Agent 이미지는 자동 준비한다.
- 설치 완료 시 실행 가능한 도구를 확인하고 API 없는 최소 데모를 실행한다.
- 실제 모델 호출은 사용자가 `live`를 실행할 때만 수행한다.
- 구현과 필요한 검증을 마친 후 커밋·푸시·PR을 생성한다. 병합은 별도 승인 대상이다.

## 현재 문제

`scripts/dev.py`에 setup/doctor/smoke/live가 있으나 ACE 예제 준비에 집중되어 있다.
doctor는 Docker 조회나 환경 lock의 첫 오류에서 종료하므로 새 checkout의 여러 문제를
한 번에 진단하지 못한다. 출력은 주로 JSON이며 복구 명령과 다음 실행 안내가 부족하다.
setup은 uv와 실행용 Python이 이미 있다고 가정하고, 긴 작업의 진행 상황은 로그에만 남는다.
README의 코어 시작과 공식 예제 시작은 개발자가 직접 선택·조합해야 한다.

## 구조와 접근 방식

기존 진입점을 확장한다. 별도 설치 프레임워크나 대화형 마법사는 추가하지 않는다.

- `Makefile`: 명령 별칭과 기본 도움말만 제공한다. 설치·진단 판단을 복제하지 않는다.
- `scripts/bootstrap.sh`: Python/make가 없어도 실행할 수 있는 POSIX shell 시작점이다.
  uv·Python 준비와 Python 진입점 실행에 필요한 최소한의 역할만 담당한다.
- `scripts/dev.py`: 명령 파싱, 코어 개발환경 점검, 진단 집계·출력, 개발 명령 실행을 담당한다.
  진단 코드가 커지면 `scripts/`의 단일 helper 모듈로 분리하되 플러그인 프레임워크는 만들지 않는다.
- `examples/ace-rtl/environment/`: 기존 소스·데이터·driver·이미지 설치와 실행 점검을 재사용한다.
  ACE/CVDP 전용 판단은 이 위치에 유지한다.

제품 CLI와 Optimizer 계약은 이 개발환경 변경의 대상이 아니다.

## 사용자 명령

| 명령 | 동작 |
|---|---|
| `make`, `make help` | 사전 요구사항, 명령 설명, 첫 실행 순서, 옵션 전달 예시 표시 |
| `make setup` | 전체 개발환경 설치, doctor, 최소 데모 실행 |
| `sh scripts/bootstrap.sh setup` | make 또는 Python이 없는 환경의 동일 설치 시작점 |
| `make doctor` | 설치 없이 가능한 진단 전체 수행, 항목별 상태와 복구 안내 |
| `make doctor ARGS="--json"` | 자동화용 진단 JSON 출력 |
| `make test` | 프로젝트 가상환경에서 전체 unittest 실행 |
| `make lint` | 프로젝트 가상환경에서 Ruff 실행 |
| `make demo` | API·Docker 없는 최소 합성 데모 실행 |
| `make smoke` | 기존 실제 RTL/CVDP 정답·오답 검증 |
| `make live` | 명시적 모델·인증 설정으로 기존 실제 모델 예제 실행 |

기존 `python3 scripts/dev.py setup/doctor/smoke/live` 진입점은 유지한다.
`--offline`과 `--platform`도 해당 명령에서 유지하고 잘못된 옵션 조합은 도움말과 함께 거부한다.
help는 환경 설치나 Docker 조회 없이 동작한다. test/lint/demo는 Docker를 요구하지 않는다.
개발 명령이 환경 부족으로 실행 불가능하면 setup 명령을 안내하고 실패한다.

## Bootstrap과 setup 흐름

1. 저장소 위치를 스크립트 기준으로 결정한다. 다른 작업 디렉터리에서도 실행 가능하다.
2. 지원 OS, Git, Docker CLI·daemon·Compose를 점검한다. 부족한 사전 조건을 모아서 안내한다.
   make가 없으면 직접 shell 명령을 사용할 수 있음을 안내한다.
3. 기존 uv를 확인하고, 없으면 버전이 고정된 공식 installer로 사용자 권한에서 설치한다.
   기존 CI의 uv 0.10.7을 새 설치 기준으로 사용하며 사용자 shell 설정을 수정하지 않는다.
   설치된 실행 파일의 경로를 명시적으로 연결해 새 터미널 없이 계속 실행한다.
   다운로드 도구가 없으면 curl/wget 설치 방법을 안내한다.
4. uv로 Python 3.12와 프로젝트 `.venv`의 frozen 개발 의존성을 준비한다.
   Python이 없는 초기 환경에서도 shell bootstrap이 이 단계를 시작할 수 있어야 한다.
5. 기존 예제 setup으로 고정 소스·데이터, 별도 driver 환경, Docker 이미지를 준비한다.
6. 통합 doctor를 실행하고 최소 데모의 정상 종료를 확인한 뒤 완료·결과 경로·다음 명령을 표시한다.

각 단계의 시작·완료와 긴 작업의 로그 위치를 출력한다. 오류에는 실패 단계와 복구 명령을 포함한다.
성공한 준비 작업은 보존하여 재실행 시 재사용한다. 기존 Docker build cache와 검증된 다운로드를
재사용하되, 재실행을 이유로 기존 checkout을 강제 초기화하거나 가상환경을 삭제하지 않는다.
실패 뒤 다른 플랫폼·모델이나 합성 평가로 대체하지 않는다.

offline은 bootstrap을 포함하여 다운로드·이미지 빌드로 부족한 환경을 보완하지 않는다.
검증된 로컬 도구·소스·데이터·이미지와 캐시만 사용하며 부족한 항목은 오류로 보고한다.

## Doctor 계약

doctor는 의존성 설치, 소스 수정, 이미지 다운로드, 모델 호출을 하지 않는다.
독립적인 검사를 계속 수행하고 선행 조건이 없어 수행할 수 없는 검사는 검사 불가로 표시한다.
Python 자체가 없거나 지원 버전 미만이면 shell 진입점에서 해당 문제와 bootstrap 명령을 안내한다.

검사 범위:

- 코어 개발: 지원 실행 환경, Git, uv, 프로젝트 Python, 가상환경·패키지·개발 도구 실행 가능 여부.
- Docker 평가: CLI, daemon 접근·권한, native 플랫폼, Compose, 환경 lock 형식,
  고정 소스와 데이터, driver Python·의존성 lock, 이미지 identity/platform, 실제 도구 실행.
- 모델 실행: 필수 인증 환경변수의 존재 여부, 명시적 무료 모델 설정의 유효성.
  설정 확인은 endpoint 접속이나 실제 inference 성공으로 표시하지 않는다.

각 검사 결과는 안정적인 ID, 영역, 상태(`ok`, `error`, `blocked`), 짧은 설명,
해결 안내를 가진다. `blocked`에는 필요한 선행 조건을 명시한다.
코어·평가 환경 준비와 live 설정 상태를 구분해 요약한다. live 인증 부재는 기본 setup/doctor의
실패 원인이 아니며, 전체 개발환경의 필수 코어·평가 검사가 실패하면 doctor는 nonzero를 반환한다.

일반 출력은 사람이 읽는 요약이며 `--json`은 단일 JSON 문서만 stdout에 쓴다.
진단용 subprocess는 시간 제한을 적용하고 raw 로그와 자격증명 값을 출력하지 않는다.
손상된 lock, 도구 누락, timeout은 traceback 대신 해당 항목의 진단으로 표시한다.
진단 성공은 실제 smoke나 모델 실행 성공을 의미하지 않는다.

## Help와 문서

README 상단에 사전 조건 → 한 명령 설치 → doctor → 첫 데모 → 담당 영역 순서를 배치한다.
CONTRIBUTING에는 일상 개발 명령, 가상환경 접근, 기존 직접 실행 명령과의 관계를 설명한다.
온보딩 가이드에는 Mac/Ubuntu의 Git·Docker·Compose·make 설치 안내와 흔한 복구 절차를 둔다.
Docker 미실행·접근 권한, PATH, 데이터/이미지 부족, lock 불일치, offline 부족,
모델 인증 부재를 실제 진단 메시지와 연결한다. 비밀 값은 예시·로그에 기록하지 않는다.

## 검증과 완료 기준

- 새 checkout에서 help가 Python 의존성·Docker 없이 출력된다.
- bootstrap의 uv/Python 없음, 사전 도구 누락, download 실패, offline 경로를 격리 테스트한다.
- doctor가 복수 문제를 수집하고 의존 검사만 blocked 처리하며 복구 안내와 JSON·종료 코드를 검증한다.
- 손상된 환경 lock, Docker 중지·timeout, 이미지·driver drift, 키 부재를 회귀 테스트한다.
- setup 순서, 오류 시 중단, 재실행, 작업 디렉터리 독립성을 검사한다.
- 전체 unittest, lint, 최소 데모와 Makefile 진입점을 실행한다.
- 가능한 로컬 환경에서 실제 setup → doctor → offline setup → smoke를 검증한다.
  Ubuntu 검증은 원격 CI의 실제 결과와 구분하여 기록하고, 불가능한 검증은 사유와 함께 남긴다.
- 테스트의 skip과 실도구 검증을 구분하고 결과를 `docs/verification.md` 및 PR에 요약한다.

## 설계 참고

기존 저장소의 고정 소스·driver lock·이미지 검증을 그대로 사용한다.
uv 공식 문서(Context7 `/astral-sh/uv`, 2026-09-21 확인)의 버전별 standalone installer,
`UV_INSTALL_DIR`/`UV_NO_MODIFY_PATH`, Python 자동 준비 및 offline 동작을 참고했다.
실제 구현에서는 고정 uv 버전에서 사용하는 옵션과 경로를 검증한다.
