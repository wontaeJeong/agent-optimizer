# 독립 설치 CLI와 선택형 연동의 단일 실험 흐름

## 배경과 목표

개발자는 `agent-optimizer` 소스 저장소에서 코어 계약·팀 플러그인을 개발한다. 앱 사용자는
저장소 없이 Python 패키지의 `agent-opt` CLI/TUI만 설치할 수도 있다. ACE-RTL 스킬 프로필과
CVDP는 첫 실사용 예제이지 모든 사용자에게 필요한 기본 Agent/데이터셋은 아니다. 사용자는
로컬 또는 고정 Git Agent와 다른 데이터셋·명시적 평가기를 같은 최적화 계약에 연결할 수 있어야 한다.

현재 wheel은 `src/agent_optimizer`와 실행 스크립트만 설치하지만 `Registry.load_project()`는
저장소의 모든 `examples/`와 `experiments/` 파일을 조회한다. 소스 밖 검증도 `--help`만
실행하고, 데이터셋 목록·새 실험·실제 실행은 저장소 경로에 의존한다. ACE는 아직 준비되지 않은
benchmark 때문에 `load_experiment()`/`doctor --plan`이 먼저 실패할 수 있고, 준비된 경우에도
CLI → shell bootstrap → 개발용 Python 명령 → 예제 runner로 다시 진입한다.

**목표:** wheel만 설치한 앱 사용자에게 목록 → 명시적 Agent·데이터셋 선택 → 필요한 자산의
승인 후 준비 → 진단 → 실행 → 보고서가 이어지게 한다. 개발용 저장소 경로와 앱 사용자 경로는
동일한 실행·평가 구현을 사용하되 설치/검증 책임은 분리한다.

## 선택과 범위

1. **선택: 가벼운 코어 패키지 + 버전 고정 선택형 연동.** wheel에는 공통 계약·runner·CLI·
   내장 Optimizer/Harness, ACE/CVDP·Verilog-Eval 등 선택형 항목의 식별 정보·고정 출처만 둔다. 선택형
   연동 코드는 사용자 동의 후 고정 버전으로 가져온다. 다른 Agent/데이터셋은 명시된 사용자
   소스와 채점기 계약으로 연결한다.
2. ACE/CVDP 파일 전체를 wheel에 넣는 방식은 선택하지 않은 사용자에게도 도메인 자산을
   배포한다. 선택 후 모든 연동 저장소를 수동으로 clone하게 하는 방식은 준비 단절을 남긴다.
3. 별도 `./dev`를 추가하지 않는다. 개발용 `make`/POSIX bootstrap은 Python·의존성 설치와
   개발 검사/호환 진입점이고, 앱 사용자의 공용 진입점은 설치된 `agent-opt`다.

이번 작업은 설치된 코어 CLI의 실제 기능, 첫 선택형 ACE/CVDP 연결, 사용자 Agent·데이터셋
경로, 검증 구분까지 다룬다. 원본 ACE native runner, 모든 Agent 자동 호환, 데이터셋 자동
추천, 모델 성능 향상 보장은 포함하지 않는다.

## 구성 요소와 소유권

| 단위 | 책임과 의존성 |
|---|---|
| 패키지 카탈로그 | 선택 가능한 첫 연동 ID, 호환 계약 버전, 연동 코드를 가져올 Git URL·전체 commit 및 검토된 자산 무결성 근거를 소형 메타데이터로 제공한다. 조회만으로 저장소 clone·Docker·연동 Python 코드를 실행하지 않는다. 고정 출처는 릴리즈 검토 없이 갱신하지 않는다. |
| `Registry` | 패키지 내장 알고리즘·하네스와 **명시적으로 선택된** 파일 플러그인만 해석한다. 설치된 CLI가 `cwd`에서 저장소의 모든 예제를 찾지 않는다. 공유 소스 marker와 프로젝트 식별이 있는 개발 checkout에서만 `experiments/<team>/`의 ID→구현 파일 경로를 로드하고, 일반 사용자 작업공간에서는 실험별 `[plugins.*]`만 로드한다. 알 수 없는 ID/중복 등록은 실패한다. |
| 선택형 연동 스냅샷 | ACE/CVDP 연동 파일과 필요한 빌드 문맥을 검증된 버전으로 사용자별 cache에 확보한다. 준비한 실험 작업공간에는 실행에 필요한 파일만 검증·복사하여 원본/설치 패키지를 수정하지 않는다. 임의 symlink, 경로 이탈, 불일치 버전은 거부한다. |
| 작업공간 | 사용자 선택 경로에 설정/선택 자산/결과를 보관한다. Agent는 로컬 소스 또는 고정 Git commit이며 후보는 스냅샷에서 생성한다. 평가 기준과 private 자료는 Agent workspace에 넣지 않는다. |
| 연동 lifecycle | ACE 예제의 고정 자산 준비·환경 진단·공식 평가·모델 실행을 한 Python 경로에서 담당한다. `agent-opt`와 기존 개발용 명령은 이 경로를 호출하며 shell로 서로 재진입하지 않는다. 범용 CLI는 ACE-specific Docker/채점 구현을 직접 포함하지 않는다. |

배포용 카탈로그 pin은 **먼저 게시·검증된 연동 commit**을 가리킨다. 개발 중인 로컬 예제를
시험할 때는 개발자가 명시적으로 로컬 소스를 선택하며, 앱 사용자 명령이 현재 checkout이나
원격 `main`으로 암묵적으로 대체하지 않는다. 릴리즈마다 CLI와 연동 계약의 호환 버전을
확인한 뒤 pin을 갱신한다.

연동 코드 자체를 wheel에 포함하지 않는다는 뜻이지 ACE 원본 소스·공식 CVDP 데이터·Docker
이미지를 사용하지 않는다는 뜻은 아니다. 사용자가 ACE/CVDP를 선택한 후에만 해당 공개 소스와
평가 자산을 준비한다. 데이터셋의 버전·해시, 연동 파일, 이미지 ID, Agent source revision은
실험 manifest에서 식별 가능해야 한다.
기존 Verilog-Eval의 고정 버전 선택·준비도 같은 선택형 경계를 유지한다.

## 앱 사용자 흐름

1. 새 가상환경 등에 wheel을 설치한다. 저장소 clone이나 Docker 없이 `agent-opt --help`,
   `agent-opt datasets list`, `agent-opt tui`의 첫 화면 및 명시적 사용자 로컬 구성 확인이
   동작한다. 설치 패키지 경로에 결과나 자격증명을 쓰지 않는다.
2. TUI에서 사용자가 **ACE-RTL + CVDP 예제** 또는 **내 Agent/내 데이터셋**을 직접 고른다.
   ACE 선택에는 CVDP가 연동된 예제임을 명시하고, 이를 범용 기본 데이터셋으로 자동
   추천하지 않는다. 다른 Agent는 소스·실행 하네스·editable 범위를, 다른 데이터셋은
   tasks 파일/등록 provider와 분리된 채점기 파일/ID를 명시적으로 받는다.
3. ACE 예제를 처음 선택하면 최소 선언과 연동 ID/버전만으로 미준비 자산을 먼저 식별한다.
   아직 없는 benchmark 파일을 요구하는 `load_experiment()`나 정적 `doctor --plan`을
   이 단계의 성공 조건으로 쓰지 않는다. 작업공간과 다운로드·Docker 빌드 대상을 보여주고
   확인받아 준비한다. 완료 후 정상 실험 설정을 만들거나 검증하여 같은 `doctor --plan`을
   실행하고, Docker/driver/고정 이미지의 읽기 전용 실도구 진단을 수행한다.
4. 자격증명은 모델 API 인증 키/토큰(현재 `AGENT_OPT_MODEL_API_KEY`)이며 환경 또는
   credential store/숨김 세션 입력으로만 제공한다. 정적·평가환경 진단에서 실제 모델을
   호출하지 않는다. 모델 연결 검사는 명시적으로 승인한 경우에만 실행한다.
5. 실험/예산과 준비 상태를 보여 준 뒤 최종 실행을 확인한다. 기존 runner가 train 평가,
   후보 생성, validation 선택, 선택 고정 후 test 및 `report.html` 작성을 맡는다. ACE 예제도
   같은 실행 근거를 사용하며 native ACE runner라고 표시하지 않는다. 종료 시 결과 경로와
   실패/미검증 영역을 분리해 보여 준다.

비대화형 CLI는 `agent-opt init --profile ace-rtl --workspace PATH`로 **미준비 선언**을 생성한
뒤 `agent-opt prepare PATH/experiment.toml [--offline]` →
`agent-opt doctor --plan PATH/experiment.toml` → `agent-opt run PATH/experiment.toml`을 사용한다.
미준비 `experiment.toml`에는 카탈로그의 ID·pin과 예정된 상대 경로를 명시한다. `prepare`는
파일을 모두 요구하는 `load_experiment()`보다 앞서 이 선언의 버전/경로를 검증하여 자산을
준비하고, 끝나면 기존 실험 계약으로 다시 검사한다. 준비 전 `doctor --plan`은 잘못된
실험이라고 뭉뚱그리지 않고 `준비 필요`와 `prepare` 명령을 **읽기 전용**으로 보고한다.
`prepare` 호출 자체가 자산 준비에 대한 명시적 선택이다. TUI와 CLI는 동일한 준비 함수를
호출한다. `run`은 다운로드·설치·다른 모델 호출을 시도하지 않으며 준비 부족 시 필요한
`prepare`/진단 명령과 함께 실패한다. 예제 외 사용자 설정은 기존
`init --agent ... --dataset ... --evaluator ...` 경로를 유지한다.

## 오류·재현성·보안 경계

- 선택형 연동은 사전에 검토한 고정 Git commit과 파일/아카이브 무결성으로 검증한다.
  cache에 버전별로 준비하고 완전한 검증 후에만 게시한다. `--offline`에서는 기존 검증된
  cache만 재사용하며 누락·불일치 시 실패한다. 재실행은 사용자 파일을 덮거나 변경된
  원본 Agent를 초기화하지 않는다.
- 정적 계획, 환경/공식 채점기 smoke, 실제 모델/Agent 실험을 구분한다. 준비/정적 진단
  성공으로 공식 평가나 최적화 성공을 주장하지 않는다. 오류 원인·수정 명령을 표시하고
  미구현·미지원 경로는 baseline/합성 결과로 대체하지 않는다.
- 실행 argv는 배열과 `shell=False`를 사용한다. 자격증명은 설정/로그/다운로드 아카이브에
  남기지 않고, 환경 및 credential store/세션 범위만 사용한다. custom evaluator 없이
  임의 사용자 데이터셋을 자동 채점하거나 여러 데이터셋 점수를 합산하지 않는다.

## 검증과 구현 순서

1. **설치 패키지 독립성:** sdist/wheel을 격리 venv에 설치하고 소스 저장소 밖 임시 cwd에서
   데이터셋 목록, TUI 시작, 사용자 로컬 Agent·JSON 데이터셋+명시적 evaluator의
   init/plan/run/report를 확인한다. 호스트 개발용 `.venv`, `PYTHONPATH`, 저장소 `examples/`
   접근 없이 통과해야 한다.
2. **선택형 연동:** 격리된 고정 Git fixture로 선택 전 무다운로드, 올바른 pin/해시, 잘못된
   revision·누락 cache의 실패, 완료 전 부분 자산 미게시, 정적 진단과 실제 준비의 차이를
   검사한다. TUI와 CLI가 같은 자산/선택 manifest를 기록하고 동일한 lifecycle을 사용한다.
3. **실행환경:** `make setup-core`·`make test`·`make lint`는 개발 증거다. ACE 연동에서
   실제 Docker 이미지·driver·공식 CVDP 정답/오답 smoke는 별도 증거다. 모델 연결과
   ACE 최적화는 API 설정이 있는 환경에서만 실행 결과/보고서로 확인한다. CI의 일반
   wheel job·선택형 공식 평가 job·실모델 실행의 skip/차단/통과를 섞지 않는다.

패키지 독립성을 먼저 확보하고, 그 계약 위에 선택형 ACE 연동과 단일 준비·실행 lifecycle을
연결한다. 기존 개발용 명령은 호환을 유지하면서 같은 lifecycle에 위임한다. 변경 후 문서와
실제 명령/환경/결과를 함께 갱신하며 외부 출처의 SHA를 자동 갱신하지 않는다.
