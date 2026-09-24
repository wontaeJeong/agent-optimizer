# 준비 상태 후속 설계

## 목표와 검증 경계

중첩된 Optimizer 설정을 사용자 실험 설정으로 생성할 수 있게 하고, 대체 Git·패키지
전송 경로와 자체 러너 CI의 준비 조건을 작은 범위에서 검증한다. 기존 CLI/TUI, 명시적
데이터셋 선택, 공통 계약, 고정 source commit·데이터 해시, 선택적 네트워크 설정을 유지한다.
합성 fixture는 연결 검증일 뿐 실제 Agent 성능의 근거가 아니다. 이 환경에서는 모델
endpoint·자격증명과 원격 러너가 준비되지 않았으므로 ACE live/원격 CI 성공을 주장하지 않는다.

## 사용자 실험 설정 생성

`agent-opt init --optimizer-config`는 Optimizer ID별 객체를 받으며,
`file_variants.variants`처럼 객체를 담은 배열도 허용한다. `setup_wizard.py`는 JSON 객체
문법을 TOML 안에 그대로 넣는 대신 유효한 TOML literal로 직렬화한다. inline table에는
`=`를 사용하고 문자열은 이스케이프하며, 생성 결과는 기존 `load_experiment`로 검증한다.
새 설정 디렉터리를 만든 뒤 생성·검증이 실패하면 이번 호출에서 만든 디렉터리만 정리해
같은 이름으로 재시도할 수 있게 한다. 기존 디렉터리와 별도 데이터 준비 cache는 보존한다.
복수 데이터셋은 앞서 생성한 설정과 새 session 파일도 함께 정리하되 기존 파일은 보존한다.
중첩/단순 설정, 잘못된 값, 합성 Agent와 file-variants의 CLI init/doctor/run/report를 확인한다.

## 전송 경로와 CI

별도 mirror 관리자 대신 기존 도구 설정을 활용한다. Git URL rewrite 또는 명시적 고정
Agent URL, uv/pip index 환경변수, Docker daemon/registry 설정, 기존 선택적 proxy·전체
CA bundle을 사용한다. 재작성한 Git 소스도 요청한 commit이어야 하고 내려받은 데이터도
고정 해시와 일치해야 한다. 예제의 공개 기본 URL 및 원본 주소에 접근할 수 없을 때의
검증된 cache 준비 조건을 문서화한다. 전송 경로를 바꿨다는 이유로 pin을 갱신하거나
검사를 우회하지 않는다. 기존 `uv.lock`의 공개 절대 URL은 index 환경변수만으로 바뀌지
않으며, 검증된 cache 재사용이나 검토한 lock 재생성이 필요하다. 데이터만 미리 준비했다면
첫 setup은 online 경로로 실행한다. 자격증명 없는 로컬 Git 저장소로 rewrite를 검사하고 가능한
proxy/CA 계약 테스트를 실행한다.

기존 workflow는 `CI_RUNNER_LABELS`를 지원하며 자체 러너에서 simulator 도구를 확인한다.
실제 결함이 확인된 경우에만 workflow를 수정한다. 러너 도구·의존성/Action 접근·proxy/CA·
artifact 보존의 책임과 필요한 설정을 명시한다. 일반 CI는 모델 없이, 공식 Docker 통합은
명시적 선택으로 유지한다. 같은 로컬 명령과 workflow 문법을 확인하되 로컬 성공을 원격
CI 성공으로 표현하지 않는다.

## 검증 및 완료 조건

회귀 테스트, `make lint`, 전체 테스트, 합성 CLI init/doctor/run/report, core doctor 및
관련 패키징 검사를 실행한다. 건너뛴 검사와 외부 환경 차단을 기록한다. 추후 모델 endpoint와
자격증명이 준비되면 ACE setup/doctor/smoke, 모델 연결 검사, 작은 live 실험을 실행하고
합성 결과가 아닌 실제 보고서를 비교한다. 원격 러너의 성공은 해당 workflow 실행으로
별도 검증한다. 인증정보·proxy 값·비공개 endpoint 세부정보를 프로젝트 파일이나 결과에
저장하지 않는다.
