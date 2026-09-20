# 프로젝트 인수인계 컨텍스트

요구사항의 출처는 **사용자가 제공한 v0.3.0 인수인계 내용**이다. 초기 프로젝트는 ChatGPT와
요구사항을 논의한 뒤 만들어졌고, 전달 파일명은 `agent-optimizer-v0.3.0.zip`이었다.
이 문서는 확정 요구사항과 설계 의도를 보존한다. 외부 기술 사실은 [SOURCES.md](SOURCES.md),
현재 구현과 검증 수준은 [status.md](status.md)를 기준으로 구분한다.

## 배경과 제품 목적

다른 사업부의 RTL 디버깅 Agent에 구조적 비효율, 과도한 토큰 사용, 느린 실행 문제가 제기됐다.
그 Agent의 내부 구조와 Harness는 아직 정확히 알 수 없다. OpenCode, Claude Code, Codex,
자체 Harness 또는 sub-agent 구조일 수 있으므로 특정 구조를 전제하지 않는다.

먼저 Optimizer 연결로 개선 가능성을 보여주는 데모를 만들고, 다른 팀 Agent에도 적용할 수 있는
**범용 Agent Optimizer**로 확장한다. RTL 디버깅은 첫 적용 분야, ACE-RTL은 기본 데모 대상,
CVDP는 RTL 데모의 벤치마크·평가 환경이다. ACE-RTL 데모만으로 타 사업부 Agent 개선을 입증한 것은 아니다.
새 대상의 소스·실행·평가·수정 허용 범위를 연결해야 하며, 대상에 따라 어댑터 개발이 필요하다.

## 확정 요구사항

- **환경과 규모:** Linux 개인 개발 서버의 Python CLI. Docker와 외부 저장소·의존성 사용 가능.
  팀원들이 함께 개발·데모하는 초기 단계이며 웹 UI, 분산 실행 플랫폼, 서비스 운영 체계는 현재 요구사항이 아니다.
- **팀 통합:** 알고리즘별 담당, Agent 구성 담당, 시뮬레이터/평가 담당의 작업을 하나의 중심 repo에서 통합한다.
  공통 입력·후보·평가 결과는 `contracts.py`로 맞춘다. 작은 기능마다 디렉터리·추상 클래스·프레임워크를 늘리지 않는다.
- **Optimizer:** GEPA, Meta-Harness, Ecdysis 등은 검토·연결 후보이며 구현 완료를 뜻하지 않는다.
  알고리즘을 선택·조합할 수 있어야 한다. 변경 대상은 프롬프트뿐 아니라 설정, 코드, 실행 흐름,
  역할 분담, sub-agent 구성까지 대상 Agent가 허용하는 범위다.
- **변경 권한:** 원본 Agent repo를 직접 수정하지 않고 후보 스냅샷에서 변경한다.
  평가 기준·평가 테스트를 바꿔 점수를 높여서는 안 된다. Agent 구성 파일과 Agent가 생성하는 RTL 산출물을 구분한다.
- **Harness:** OpenCode 우선 연결. Claude Code, Codex, OpenAgent, 자체 Harness 확장 여지를 두되,
  이름 등록이나 계약만으로 지원 완료라고 하지 않는다. 미구현 기능은 명시적으로 실패시킨다.
- **복수 Agent:** 여러 팀의 독립 Agent와 한 Agent 내부 sub-agent는 다른 개념이다.
  독립 Agent별 원본 버전, 후보 계보, 설정, 결과를 식별한다.
- **실험:** Agent·Harness·Optimizer·평가 방법·모델·지표·예산을 실험별로 정한다.
  성공률·토큰·시간·비용을 비교하고, 미수집 값은 `None`/`null`로 표시한다.
  Agent 사용량과 Optimizer 자체 사용량을 구분한다. baseline과 후보는 동일한 평가 조건으로 비교한다.
- **재현과 선택:** 소스 버전/hash, 변경 diff, 설정, 평가 결과를 보존한다.
  validation으로 선택하고 test는 선택 고정 이후에만 사용한다. 합성 데모 점수는 실제 성능·세일즈 수치가 아니다.

## 주요 결정과 이유

| 확정 결정 | 이유와 적용 경계 |
|---|---|
| 실제 대상 Agent는 별도 repo | 다른 팀의 소유권·버전을 보존한다. URL + 고정 commit 또는 로컬 checkout, 실행법, editable 범위, 평가 연결이 필요하다. |
| 작은 개발 예제는 중심 repo 내부 | 팀원이 외부 Agent/API 없이 공통 계약을 개발할 수 있는 의도적 예외다. `minimal`은 합성 연결 검증, `rtl-debugger`는 수정하기 쉬운 작은 RTL 예제다. |
| `ace-rtl`에는 연결 자산을 포함 | 설정·어댑터·준비 스크립트·문서를 포함한다. upstream 전체 소스를 vendoring하지 않고 다운로드는 `external/` 등 Git 제외 영역에 둔다. |
| 도메인 코드는 `examples/`에 둠 | ACE-RTL/CVDP/RTL 시뮬레이터나 고객별 분기가 제품 코어에 누적되는 것을 막는다. 코어는 범용 계약·실행·평가 연결을 담당한다. |
| 공식 CVDP OSS Docker 환경 우선 재사용 | Icarus·Verilator·Yosys별 중복 설치 체계를 피한다. Agent/Harness 환경, CVDP 평가 환경, 그 내부 시뮬레이터는 별개다. |
| 상용 EDA 전부 제외 | Xcelium·IMC 등 상용 어댑터·설치·라이선스 설정을 만들지 않는다. `no_commercial` 계열에서도 실제 과제 의존성을 확인하고 제외 사유를 기록한다. LLM API 비용은 별개다. |
| 단순한 Python CLI와 현재 모듈 구조 유지 | 여러 담당자가 작은 공통 계약으로 통합하는 초기 단계다. 기능 검증보다 프레임워크 구축이 앞서지 않도록 한다. |
| 개인 설정·비밀정보 Git 제외 | `.claude/`, `.codex/`, `.vscode/`, `.idea/` 등은 개인 환경이다. 공유 `AGENTS.md`/필요시 `CLAUDE.md`, `.env.example`은 포함 가능하나 실제 `.env`·인증정보는 제외한다. |

## 초기 구현 선택 — 요구사항으로 승격하지 않을 것

- **ACE OpenCode 스킬 프로필:** v0.3.0은 OpenCode가 ACE 스킬을 읽고 공개 과제를 수행한 뒤
  외부 CVDP evaluator가 채점하는 방식을 택했다. 사용자가 원본 ACE 실행을 이 방식으로
  반드시 대체하도록 요구한 것은 아니다. [실행 차이와 주장 범위](status.md#ace-rtl-실행-프로필)를 확인한다.
- **한 문제 validation-only smoke:** 현재 ACE 데모의 초기 범위다. 최종 연구 평가 범위가 아니다.
- **`baseline`/`file_variants`:** 무변경 기준선 및 명시적 파일 변형의 연결 예제다. 연구 알고리즘을 대체하지 않는다.
- **전체 Agent × Harness 조합, 순차 stage 실행, 텍스트 파일 생성·교체:** 현재 구현 범위다.
  임의 조합 지원이나 모든 구조 변경이 이미 가능하다는 뜻이 아니다.
- **개발 환경과 CI:** Docker daemon native 플랫폼을 기본 선택하고 명시적 override만 허용한다.
  코어 CI의 apt Yosys/Icarus는 빠른 회귀 검증용이며 공식 CVDP 이미지는 수동 integration에서 검증한다.
  CVDP Python 3.12 driver의 전이 의존성 lock은 예제에 두며 코어에 패키지 관리 프레임워크를 추가하지 않는다.
  Mac Docker ARM64와 Ubuntu x86_64에서 실제 평가를 확인했다. `10baa46`의 native 코어 CI와
  공식 setup/offline/smoke·provider config 재검증은 통과했다. live 모델은 API 키 부재로 미검증이다.

## 미결정 항목

1. 실제 타 사업부 Agent의 소스 접근, Harness/sub-agent 구조, 실행법, 평가법, editable 범위.
2. 대표 ACE 데모를 스킬 프로필로 할지 원본 runner 프로필로 할지, 무엇을 개선했다고 주장할지.
3. 첫 연구 Optimizer의 정확한 논문·공식 구현·고정 버전과 본 프로젝트 계약에 연결할 범위.
4. 실험에 쓸 OpenCode 버전·모델·예산·지표 우선순위, 전체 사용량 수집 방법,
   일반화 평가용 train/validation/test 데이터와 family 분리.

구현 순서와 완료 기준은 [NEXT_STEPS.md](NEXT_STEPS.md)에 둔다. API/플러그인 연결법은
[adding-components.md](adding-components.md), 담당 영역은 [CONTRIBUTING.md](../CONTRIBUTING.md)를 따른다.
