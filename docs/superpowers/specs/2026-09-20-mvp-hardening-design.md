# MVP 신뢰성 보강과 재현 가능한 개발 환경

작성일: 2026-09-20. 상태: 사용자 승인, Task 1–6 구현 및 로컬 통합 검증. Ubuntu/live 검증은 남음.

## 1. 목표와 접근

기존 Python CLI, 평평한 코어 모듈, `contracts.py`와 파일 플러그인 구조를 유지한다.
아키텍처 검토에서 발견한 8개 문제를 해결하고, 팀원이 Optimizer를 연결할 수 있는
실행 가능한 계약 테스트와 Docker 기반 실환경 검증 경로를 제공한다.

세 접근을 비교했다.

1. 결함만 수정: 작지만 실제 평가와 팀원 연결의 검증 공백이 남는다.
2. **기존 구조 보강 + 재현 가능한 한 문제 smoke:** 이번 작업의 선택안.
3. 새 플랫폼/플러그인 프레임워크: 현재 MVP 규모에 비해 비용과 추상화가 과도하다.

상세 최적화 알고리즘은 팀원이 담당한다. Meta-Harness를 첫 연결 검토 대상으로 하되,
GEPA/Ecdysis 등도 같은 계약으로 연결한다. 이름 등록이나 모의 실행을 알고리즘 지원
완료로 표시하지 않는다. 추가 Harness, native ACE, 분산 실행, resume는 이번 범위에 없다.

## 2. 구성과 데이터 흐름

```text
환경 준비: 고정 소스/데이터 확보 → 해시·출처 기록 → 이미지 준비 → 실제 evaluator smoke
실험: source → 등록된 candidate → trial workspace → Harness → 산출물 수집 → Evaluator
선택: train 탐색 → validation 선택 → 선택 고정 → 선택적 test → 결과/보고서
```

- 코어: 설정 검증, 소스/후보 관리, 실행·예산, 지표·선택, 결과 저장.
- 예제: ACE 스킬 프로필, CVDP 준비/채점, 작은 RTL 예제의 검증 코드.
- 개발 명령: 의존성 준비·CVDP 확보·Docker 빌드·smoke를 연결하는 작은 스크립트.
- 모델 설정: 기존 OpenCode Harness의 provider/model 설정과 환경변수를 사용한다.
  모델 API 주소·모델명·인증을 교체하기 위해 별도 모델 게이트웨이를 만들지 않는다.

## 3. 8개 발견 사항의 처리

| 항목 | 설계 결정 | 필수 검증 |
|---|---|---|
| 산출물 루트 symlink | Agent 종료 후에도 파일시스템 입력을 다시 검증한다. 수집 루트와 경로의 symlink/경로 이탈을 거부하며 호스트 파일을 복사하지 않는다. | 루트 링크, 내부 링크, 정상 파일 수집 |
| 전역 예산으로 단축된 trial | trial 자체 timeout과 실험 예산 소진을 구분한다. 전역 예산 때문에 중단된 trial은 성능 실패로 선택에 사용하지 않는다. | baseline/후보 시간 조건, 마지막 trial 중단 상태 |
| RTL 성공 문자열 위조 | 작은 RTL 예제의 성공 근거를 신뢰한 검사 실행·완료 결과로 바꾼다. 제출 RTL의 stdout 문자열만으로 통과하지 않는다. | 정상/오답, 성공 문자열 출력 후 조기 종료 |
| 후보 식별·hash | CandidateStore의 발급 기록을 기준으로 ID·경로·hash·계보를 검증한다. 동일 ID의 다른 내용과 미등록 후보를 거부한다. | ID 충돌, editable 밖 변경 후 hash 재작성, 정상 계보 |
| 중단 시 사용량 누락 | usage를 기록 시점에 이벤트로 저장한다. 현재 그룹의 부분 결과와 중단 원인을 summary에 포함한다. | 사용량 보고 후 예산 중단/예외, partial 보고서 |
| 평가 의존 코드 hash | 플러그인이 사용하는 로컬 의존 파일을 명시하고 함께 fingerprint한다. 기존 문자열 플러그인 등록을 호환 유지한다. | 의존 평가 코드만 변경해도 fingerprint 변경 |
| 외부 Agent 설정 제거 | 개인 설정의 기본 제외는 유지하되 명시적으로 선택한 대상 Agent 실행 자산을 포함할 수 있게 한다. 인증 파일·환경 비밀은 제외한다. | 기본 제외, 명시 포함, 인증 파일 제외 |
| Pareto keep 무시 | Pareto는 전체 frontier를 반환한다. 명시적 keep 조합은 거부하고 문서화한다. 다른 모드의 keep 동작은 유지한다. | 모드별 설정 검증·선택 결과 |

RTL 경계의 실제 도구 확인 결과: Yosys 0.40은 제한을 우회한 `$display`를 netlist의 `$write`로
보존할 수 있다. 합성 자체가 시뮬레이션 제어 코드를 모두 제거한다는 주장은 사용하지 않는다.
제한된 입력 정책(system task, initial/final 등 거부)은 필수이며 private mismatch/nonzero exit는
marker가 있어도 실패해야 한다. 이 결정을 실제 도구 characterization과 production 거부 테스트로 검증한다.

trial 상태와 split 집계 유효성은 분리한다. 환경 오류·지원 불가·전역 예산 중단을
정상 성능 결과로 만들지 않는다. 누락 사용량은 null/미보고 상태를 유지한다.
출력 경계 위반도 trial의 식별 가능한 오류로 기록한다.

## 4. Optimizer 팀원 확장 계약

`optimize(context, seeds, config) -> OptimizationResult`를 유지한다.
`propose`, train-only `evaluate`, train-only `history`, `record_usage`를 공통 API로 사용한다.
runner가 validation 선택과 final test를 소유하며 알고리즘끼리 직접 호출하지 않는다.

- 팀원용 파일 플러그인 템플릿, 입력/출력 예제, 최소 계약 테스트를 제공한다.
- Meta-Harness 연결 위치와 원본 API를 대응시킬 체크리스트를 문서화한다.
- 실제 알고리즘이 들어오기 전 실행은 명시적 미구현 오류다.
- 모의 Optimizer는 후보/피드백/usage/오류 경계 검증에만 사용하고 연구 결과로 보고하지 않는다.
- 임의의 모든 알고리즘을 무수정으로 지원한다고 보장하지 않는다. 새 요구는 작은 계약 변경으로 검토한다.

## 5. Docker와 모델 실행 환경

주 검증 대상은 Ubuntu Linux x86_64이며 Mac Docker에서도 같은 준비/실행 명령을 제공한다.
`--platform` 생략 시 Docker daemon의 native `linux/amd64` 또는 `linux/arm64`를 빌드 전에 선택한다.
명시적 override는 유지하고 미지원 플랫폼/조회 실패/빌드 실패 후 다른 아키텍처로 자동 대체하지 않는다.
이미지 platform과 실제 실행 아키텍처를 기록한다. ARM64 호스트에서 amd64 실행이 필요하면
에뮬레이션 요구와 성능 차이를 명시하고 실제 smoke로 확인한다.

- Python 실행 환경·개발 의존성은 잠금 파일과 명시한 Python 버전으로 준비한다.
  코어는 `uv.lock`, CVDP Python 3.12 host driver는 고정 upstream requirements를 변경 없이
  universal uv-compiled 전이 의존성 lock으로 만든다. 예제-local lock으로 설치/offline 확인하고
  lock hash를 기록한다. 공식 Dockerfile 내부 패키지의 완전한 hermetic build까지 의미하지 않는다.
- Agent/OpenCode 이미지와 공식 OSS CVDP 평가 이미지를 분리한다.
- Docker를 호출하는 신뢰한 호스트 준비/평가 프로세스와 Agent 컨테이너를 구분한다.
  Agent에 Docker socket이나 비공개 평가 파일을 전달하지 않는다.
- 버전/이미지 ID, 모델 설정, 데이터 hash를 결과에 남긴다. 설치 여부와 실행 가능 여부를 구분한다.
- 초기 모델은 OpenRouter 무료 모델이다. 유료 모델로 자동 대체하지 않는다.
  인증은 환경변수로 전달하고 값은 로그·manifest에 저장하지 않는다.
- 임의 비용 차단 프레임워크는 추가하지 않는다. 반복/실행 시간 한도와 중단 기능은
  무한 대기 방지와 비교 조건 재현을 위해 유지한다.

## 6. CVDP 자동 다운로드와 변환

환경 준비 명령이 공식 `nvidia/cvdp-benchmark-dataset`에서 v1.1.0
`nonagentic_code_generation_no_commercial` JSONL과 LICENSE/NOTICE를 확보한다.
고정 revision, 파일명, 내용 hash를 기록하고 재실행 시 검증된 캐시를 사용한다.
네트워크 없이 캐시/로컬 파일을 사용하는 경로도 제공한다.

- ACE/CVDP 소스의 기존 고정 SHA는 필요 근거 없이 갱신하지 않는다.
- 데이터 revision은 배포 파일 및 importer 호환성을 확인한 뒤 고정한다.
- 원본 데이터와 비공개 평가 자료는 Git 제외 경로에 둔다.
- importer는 실제 공개 파일의 스키마를 검증하고, 지원하는 OSS functional 과제만 변환한다.
- 대상 출력 파일을 확인할 수 없는 과제, 미지원 점수 방식, 상용 EDA 의존은 제외 사유를 남긴다.
- 모든 과제가 제외되거나 필수 입력이 없으면 실패한다. 합성 데이터로 대체하지 않는다.
- 최초 smoke는 한 문제 validation으로 수행한다. 연구용 split은 family 중복 없이
  명시적으로 준비하며 smoke 결과를 일반화 성능으로 해석하지 않는다.

`no_commercial`은 상용 EDA 의존 분류이며 데이터의 이용 라이선스 이름은 아니다.
공식 LICENSE는 비코드 CC BY 4.0, 코드 Apache-2.0 및 제3자 조건을 안내한다.
LICENSE/NOTICE와 문제별 의존성을 보존하며 상용 EDA 어댑터는 추가하지 않는다.

## 7. 검증과 완료 기준

1. 8개 결함의 의미 있는 회귀 테스트 및 기존 최소 데모 통과.
2. lint, 전체 unit/contract 테스트, wheel/sdist 빌드와 설치 smoke 통과.
3. Docker 안에서 작은 RTL의 정상·오답·조기 종료를 실제 시뮬레이터로 검증.
4. CVDP 자동 확보, hash/cache 재사용, supported/excluded 결과 확인.
5. 공식 CVDP 평가기로 한 문제의 정상/실패 제출을 실제 평가하고 raw result 보존.
6. 무료 API 인증이 제공되면 OpenCode → 과제 산출물 → CVDP 한 문제를 실행.
   인증/무료 모델 용량 부족이면 정확한 차단 원인을 기록하며 실행 성공으로 표시하지 않는다.
7. CI는 코어와 결정적인 로컬/Docker 검증을 담당한다. 외부 모델 호출은 명시적 통합 실행으로 구분한다.
   Python 3.11/3.12 코어 CI는 native Ubuntu Yosys/Icarus를 사용하고, 공식 Docker 평가는 기존
   `ci.yml`의 `workflow_dispatch` boolean 입력으로 분리한다. PR CI에서 live/model은 호출하지 않는다.
8. Mac Docker와 Ubuntu x86_64의 실제 검증 결과를 구분한다. 한 환경의 성공으로 다른 환경의 검증을 대체하지 않는다.

README에는 시작 명령과 한 문제 실행을, architecture에는 책임·오류·데이터 경계를,
adding-components에는 팀원 계약을, SOURCES에는 고정 출처를 반영한다.
status/verification/NEXT_STEPS는 실제 실행 결과와 남은 팀원 작업에 맞춰 갱신한다.

## 8. 설계 승인 당시 기준

- 작업 기준: origin/main `12d9caf`.
- 작업공간: `.worktrees/mvp-hardening`, 브랜치 `feat/mvp-hardening`.
- 기준 테스트: Python 3.14.5에서 32개 중 31개 통과, Icarus 미설치로 1개 생략.
- 당시 이 문서는 구현·Docker/CVDP 통합 성공 기록이 아니었다.
- 승인 후 회귀 테스트부터 구현했다. 실제 완료/차단 결과와 8개 발견 사항의 coverage audit는
  [verification.md](../../verification.md#2026-09-20-task-6-cihandoffintegration)를 따른다.
