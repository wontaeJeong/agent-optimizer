# 반복 최적화 데모와 개발 환경 정리

## 목표와 승인 범위

이번 데모의 완료 기준은 OpenAI 호환 모델을 사용하는 OpenCode가 ACE-RTL 스킬로 과제를
수행하고, 공식 CVDP 평가와 LLM 기반 지침 수정을 반복한 뒤 baseline과 선택 후보의 결과를
비교할 수 있는 것이다. ACE 원본 runner의 역할별 반복 실행을 재현하는 것은 아니다.

기존 Python CLI, 평평한 모듈 구조, `contracts.py` 계약과 파일 플러그인을 유지한다.
기존 setup/doctor/network 경로를 보강하는 방식을 채택한다. Typer 전면 전환은 마이그레이션
비용에 비해 데모에 주는 이익이 작고, 별도 TUI는 추가 상태 관리와 검증이 필요하여 제외한다.

## 모델 설정

- OpenAI 호환 chat completion API와 Bearer 인증을 사용한다. 기본 모델은
  `glm5.3-flash`이며 실행 환경에서 모델과 API 주소를 교체한다.
- 실제 서비스 주소와 토큰은 환경 설정에만 둔다. 예제는 일반화된 주소와 빈 자격증명을 쓴다.
- API base URL과 완전한 completion URL을 구분한다. 사용자 서비스의 경로를 임의로
  복수형으로 바꾸거나 중복 결합하지 않는다. OpenCode provider의 URL 구성 계약과 대조하여
  필요한 최소 연결 방식을 구현 계획에 확정한다.
- Agent와 Optimizer는 같은 기본 모델 설정을 사용할 수 있으나 역할별 사용량은 구분한다.
- 기존 OpenRouter 무료 모델 전용 live 제한을 제거하고 선택한 provider의 필수 설정을 검사한다.
  연결 실패 시 다른 모델이나 합성 실행으로 자동 대체하지 않는다.

## 단순 Optimizer와 팀 확장

`OptimizationContext`와 `Optimizer.optimize` 계약을 사용한다. 첫 구현은 연구 알고리즘의
대체 구현이 아닌 작은 LLM 피드백 예제다. 팀원은 별도 파일 플러그인을 등록하여 교체한다.

1. seed 후보를 train에서 평가한다.
2. 수정 대상 지침, train 평가 결과와 제한된 공개 피드백을 모델에 전달한다.
3. 모델이 반환한 지침을 검증하고 `context.propose`로 새 후보 스냅샷을 생성한다.
4. 새 후보를 train에서 평가하고 이 결과를 다음 수정에 사용한다. 기본 수정 반복은 3회이며
   설정으로 변경한다. 반환 후보에는 seed와 생성 후보를 포함한다.
5. runner가 validation으로 최종 후보를 선택한다. test를 설정한 경우 선택 고정 후 실행한다.

첫 데모의 수정 범위는 ACE의 지정 지침 파일로 제한한다. 허용 밖 경로·잘못된 모델 응답·
평가 환경 오류는 명시적으로 실패한다. 소스, 평가 기준, private test는 수정하지 않는다.
Optimizer에 private 평가 자산이나 test/validation 피드백을 전달하지 않는다.

반복 횟수와 요청 timeout을 제한하고 기존 trial/wall-time 예산을 유지한다. 모델 요청 전후의
예산 처리는 기존 동기 Optimizer 계약과 일치시킨다. 후보 diff, train 평가 이력, validation
선택, 중단 시 부분 결과를 보존한다. 실제 응답에서 수집한 사용량만 기록하며 누락된 사용량과
비용을 0으로 만들지 않는다. 필요한 계약 보완은 기존 플러그인 호환성을 유지하는 최소 변경으로 한다.

## ACE 데모 데이터와 결과

기존 고정 소스와 데이터 revision을 유지한다. 현재 validation-only 단일 과제를 반복 탐색에
재사용하지 않고, 지원하는 CVDP 과제 중 서로 다른 family의 작은 train/validation 집합을
명시적으로 선택한다. 정확한 과제는 고정 데이터의 지원 형태와 평가 실행을 확인하여 결정한다.
지원 형태 확인과 실제 평가 성공은 별도 결과로 기록한다.

baseline과 후보에 동일한 Agent/Harness/모델/평가 조건을 사용한다. 결과에는 성공률, 시간,
관측 가능한 Agent partial 사용량과 Optimizer 사용량, 후보 변경 내역을 표시한다.
점수 개선은 보장하지 않는다. 작은 데모의 성공을 일반화 성능이나 논문 재현으로 설명하지 않는다.

## setup과 doctor

- 하나의 명확한 setup 진입점에서 프로젝트 환경, 기존 CVDP driver, 고정 소스·데이터,
  평가·Agent 이미지 준비와 환경 검사를 연결한다. 재실행 시 검증된 자산을 재사용한다.
- 설치 전 Python/uv/Git, Docker daemon·Compose 및 CA 적용 빌드에 필요한 BuildKit/Buildx를
  검사하여 장시간 작업 뒤 필수 도구 누락이 발견되지 않게 한다.
- Ubuntu의 기존 proxy 환경과 전체 시스템 CA bundle을 재사용할 수 있게 한다. 명시적 CA
  설정을 우선하고 Ubuntu 시스템 bundle 활용 여부를 진단 결과에 표시한다.
- Docker build와 Agent/evaluator runtime에 proxy/NO_PROXY 및 컨테이너 경로에 맞춘 CA를
  전달한다. 호스트 경로만 컨테이너 환경변수에 전달하는 것으로 성공 판정하지 않는다.
- Docker daemon의 registry 접근 설정은 호스트 daemon의 기존 설정을 사용하고, 이미지
  pull 실패를 빌드 내부 proxy 실패와 구분해 안내한다.
- doctor는 도구, 준비 상태, 이미지·driver lock, CA, 평가 실행 가능 여부를 항목별로 보고한다.
  호스트 OpenCode가 없어도 Docker Harness가 준비되어 있으면 이를 오류로 취급하지 않는다.
- 명시적 모델 연결 검사에서 인증, 모델 응답과 필요한 tool calling 동작을 확인한다.
  모델을 호출하지 않은 일반 doctor 결과와 모델 연결 검증 결과를 구분한다.
- 실패 시 비정상 종료 코드와 조치 가능한 안내를 제공한다. 토큰과 proxy 자격증명을
  로그·manifest·진단 출력에 노출하지 않는다. TLS 검증을 끄지 않는다.

## CLI와 Harness 확장

현재 argparse CLI를 유지하고 setup/doctor/데모 실행의 진입점과 도움말을 정리한다.
사람이 읽을 수 있는 진행 상태와 기존 자동화용 결과 출력을 구분한다. 새 범용 CLI 프레임워크,
대화형 TUI, 별도 서비스는 추가하지 않는다.

Harness는 기존 `RunRequest -> ExecutionResult`와 registry 파일 플러그인을 사용한다.
ACE 지침 전처리와 특정 Harness 호출의 결합은 필요한 만큼만 줄인다. 새 Harness를 추가하는
템플릿과 인증·모델 설정·timeout·종료 상태·산출물·사용량 연결 계약을 제공한다.
Claude Code/Codex는 각각의 모델 프로토콜과 실행 계약을 확인한 후 연결할 수 있도록 하며,
이번에 실제 검증한 OpenCode와 추가용 템플릿의 지원 수준을 명확히 구분한다.

## 범위 축소

이번에 제외하는 신규 기능은 연구 Optimizer 구현, 병렬 스케줄러, 실행 재개, TUI, ACE native
runner와 복수 Harness 실환경 통합이다. 이미 존재하는 안정적인 공통 기능은 데모 일정만을
이유로 광범위하게 삭제하지 않는다. 데모를 막는 provider 강제 조건, 중복 진입점·설명과
불필요한 설치 요구를 우선 정리한다. 후보 격리·평가 분리·에러 처리·재현 기록은 유지한다.

## 검증과 통합

- 단순 Optimizer의 실제 반복, train-only 피드백, editable 제한, 잘못된 응답, 모델 오류,
  usage 누락과 플러그인 교체를 의미 있는 계약 테스트로 검증한다.
- 로컬 HTTP fixture로 Bearer 전달, endpoint 경로, 모델 설정 및 실패 처리를 검사한다.
- proxy/CA 전달과 기존 evaluator·source 경계 회귀를 실행한다. Docker 가능 환경에서는
  실제 setup/doctor 및 공식 평가 smoke를 수행하고 mock 검사와 구분한다.
- 전체 unittest와 최소 합성 데모, lint 및 관련 설치/패키징 검사를 실행한다.
- 실제 서비스 접근 권한이 없는 환경에서는 모델 end-to-end 성공을 주장하지 않는다.
  실행할 수 있는 doctor/live 명령과 실제 차단 사유를 남긴다.
- PR 직전에 `git fetch origin` 후 최신 `origin/main`을 작업 브랜치에 병합하고, 충돌을
  검토·해결한 최종 코드로 필요한 검증을 다시 실행한다. 최종 PR 차이와 CI를 확인하고
  사용자가 승인한 대로 PR을 머지한다. 기본 checkout은 `main`을 유지한다.
