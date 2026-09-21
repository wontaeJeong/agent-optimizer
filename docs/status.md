# 구현·검증 상태 (v0.3.0)

**2026-09-22 온보딩 최종 검증:** `4972c8f`의 CA 집계·timeout·bytecode 수정을 확인하고
`cbca34f`에서 Mac watchdog 정리 메시지를 보완했다. 로컬 **229개: 215 통과·14 skip**,
doctor/JSON·잘못된 CA 회귀·offline setup·데모·lint·shell 검사가 통과했다.
[PR #7 코어 CI](https://github.com/wontaeJeong/agent-optimizer/actions/runs/35617263750)는 Ubuntu
Python 3.11/3.12 각각 **224 통과·5 skip**이며 native 실도구 9/9·wheel 검사도 통과했다.
수동 공식 Docker job은 skipped, live 미호출이다. [최종 근거](verification.md#2026-09-22-developer-onboarding-final-verification)를 따른다.

**2026-09-21 개발환경 온보딩:** Make/shell setup·집계 doctor·일상 개발 명령과
[설치/복구 가이드](development.md)를 제공한다. `e669340` 기반 Mac ARM64에서 공개
setup → doctor/JSON → offline setup → smoke 통과. 전체 suite **200개: 190 통과·10 skip**,
Docker 실도구 **9/9**, host-Docker **1/0/0**, 공식 CVDP 정답/오답 **1/0**을 확인했다.
lint·데모·패키징·actionlint도 통과했다. 이 단계 당시 변경된 CI의 Ubuntu 원격 실행은 미검증이었으며
아래 `10baa46` 결과와 별개다. live는 호출하지 않았고 doctor의 key/model 설정이 미준비다.
정확한 명령·산출물·초기 setup 시간 제한은 [온보딩 검증](verification.md#2026-09-21-developer-onboarding-task-3)에 기록한다.

**2026-09-20 MVP hardening:** 후보/파일 경계, 실행 중단·사용량, 플러그인 hash 및 RTL 검증을 보강했다.
Mac Docker ARM64에서 공식 OSS/OpenCode 이미지를 빌드하고 host-Docker toy 및 공식 CVDP
정답·오답 평가를 실행했다. Python 3.12 driver lock 적용 후 setup/offline/smoke도 통과했다.
플랫폼 기본값은 Docker daemon native다. 첫 Ubuntu 공식 smoke의 Dockerfile 이미지 참조 실패를 수정한
`10baa46`에서 native Ubuntu x86_64 코어 CI·공식 setup/offline/smoke·provider config 검사가 통과했다.
실제 OpenCode→모델→CVDP live inference는 API 키 부재로 여전히 `blocked_auth`다.
입력 제한은 필수이며 합성만으로 임의 RTL을 정화하지 않는다.

요구사항은 [CONTEXT.md](CONTEXT.md), 외부 판단 근거는
[SOURCES.md](SOURCES.md), 실행 명령·환경·과거 기록은 [verification.md](verification.md)를 따른다.

## 현재 기능과 근거

**2026-09-21 선택적 네트워크 설정:** proxy/NO_PROXY/전체 CA bundle을 호스트 설치·소스 확보·
데이터 다운로드·이미지 빌드·Agent 실행·지원하는 평가 Compose에 전달한다.
사용법과 지원 범위는 [network.md](network.md), 실제 검증은 [verification.md](verification.md#2026-09-21-optional-network-environment)를 따른다.

아래 코어 경로는 `src/agent_optimizer/` 기준이다. **구현**은 코드 존재를,
**오프라인 검증**은 합성 실행/로컬 프로세스/모의 계약 테스트를 뜻하며 실환경 통합과 구별한다.

| 항목 | 코드 근거 | 현재 상태 |
|---|---|---|
| Python CLI·설정·플러그인 | `cli.py`, `config.py`, `registry.py`, `contracts.py` | 구현. 파일 플러그인/entry point 연결. 모든 Agent의 자동 호환을 보장하지 않음. |
| 로컬/Git 소스 스냅샷 | `sources.py` | 구현·로컬 임시 Git 테스트. Git full SHA, 원본 보존, 명시적 숨김 실행 자산 포함·인증 제외. setup의 실제 고정 ACE/CVDP checkout 확인. 모델 Agent 실행과는 별개. |
| 후보·editable·hash·diff·계보 | `workspace.py`, `runner.py:verify_candidate` | 구현·오프라인 검증. 텍스트 생성/교체, 경로 이탈·허용 밖 수정·변조 거부. |
| 독립 Agent × Harness | `config.py:load_experiment`, `runner.py:run_experiment` | 전체 조합, 순차 실행. 그룹별 후보/결과 분리, 오프라인 검증. 내부 sub-agent 자동 관리 기능은 아님. |
| baseline / file_variants | `optimizers/baseline.py`, `file_variants.py` | 실행 가능. 무변경 seed 반환 / 지정 파일 변형 열거. 연구 탐색 알고리즘이나 LLM 호출 없음. |
| 단계 조합·조건·선택 | `runner.py:GroupRunner.run`, `objectives.py` | 구현·오프라인 검증. 선행 stage 입력/validation gate, lexicographic·weighted·pareto 선택. |
| train / validation / test | `runner.py:Context`, `GroupRunner.run`, `config.py:load_tasks` | train-only 탐색 API, validation 선택, 선택 고정 후 선택적 test. family split 중복 거부. 최소 데모는 test까지 실행. |
| 결과·재현 자료 | `runner.py`, `results.py` | manifest, source-lock, 후보 diff/metadata, trial result/logs, events, frozen_selection, summary/report 저장. |
| command / OpenCode / Docker | `harnesses/command.py`, `harnesses/opencode.py`, `process.py` | argv/timeout·이벤트 계약 검증. 실제 Docker 실행, OpenCode 1.18.31 CLI/config에서 absent/default·명시 override·빈 env 확인. 실제 inference는 미검증. |
| Yosys/Icarus 예제 | `examples/rtl-debugger/{evaluator,iverilog}.py` | 제한 입력 → 합성 netlist → private 검사. 공식 ARM64·native amd64 이미지 각각 실도구 9/9 및 host-Docker 정답/오답/조기 종료 1/0/0. |
| ACE 스킬 / CVDP | `examples/ace-rtl/` | 고정 HF 다운로드·변환, 공식 LFSR reference/기능 오답의 비어 있지 않은 raw result 1/0 확인. ACE/OpenCode/model end-to-end는 키 부재로 미실행. |
| 개발 환경·CI | `scripts/dev.py`, 예제 `environment/`, `.github/workflows/ci.yml` | frozen core 및 universal Python 3.12 driver lock. `10baa46`에서 Ubuntu Python 3.11/3.12 코어 CI와 공식 setup/offline/smoke·provider config 통과. 첫 smoke 실패와 수정 후 native 증거는 검증 기록에 보존. |
| 팀 Optimizer 계약 | `experiments/optimizer-template/`, `tests/test_plugin_contracts.py` | 파일 플러그인·helper fingerprint·train 피드백·usage·checkpoint 연결점. 템플릿 실행은 명시적으로 미구현 오류. |
| GEPA / Meta-Harness / Ecdysis | `optimizers/{gepa,meta_harness,ecdysis}.py`, `registry.py` | **슬롯**. 내장 실행 등록 없음, 사용 시 not implemented 오류. 파일을 구현한 뒤에도 플러그인 등록 필요. 출처·채택 버전 미확정. |
| Claude Code / Codex / OpenAgent | `registry.py:reserved`, `harnesses/README.md` | **예정**. 전용 어댑터 미구현. command wrapper 등 별도 연결 작업 필요. |
| 비용·호출 상한 / 병렬 스케줄링 / resume | `config.py`, `runner.py` | **미구현**. checkpoint 저장은 재시작 기능을 뜻하지 않음. |

## ACE-RTL 실행 프로필

현재 경로는 `source.toml` → `runner.py:trial`이 SKILL.md를 prompt로 읽음 →
`adapter.py:ACEOpenCode`가 제한 안내를 추가 → `OpenCodeHarness`가 `opencode run` 호출 →
Agent 종료 후 `evaluator.py:CVDPEvaluator`가 제출 RTL을 공식 CVDP로 평가하는 구조다.

| 항목 | 현재 스킬 프로필 | 원본 runner를 baseline으로 삼는 경우 |
|---|---|---|
| 호출 경로 | OpenCode가 스킬·역할 자료를 참조하도록 요청 | upstream `ace_cvdp_native_runner.py` 또는 `ace_agent_runner.py`의 구체적 경로를 선택·연결해야 함 |
| 반복·피드백 | 코어는 trial당 Harness 호출 후 외부 평가. 공식 평가 피드백을 같은 trial의 ACE 역할 루프에 되돌려주지 않음 | upstream 지침의 Generator → 평가 → Reflector/Coordinator → 수정·재시작 루프를 실제 코드·trace로 확인해야 함 |
| 역할 Python 파일 | editable에 포함되지만 로컬 어댑터가 직접 import/호출하지 않음. OpenCode가 읽거나 실행하는지는 미검증 | 수정한 Generator/Debugger/Coordinator가 실제 실행됐다는 호출 근거 필요 |
| 모델·예산 | Harness model_env의 모델 및 코어 trial/시간 예산 | 역할별 모델, 시도·반복·병렬도, 내부 호출/비용과 외부 예산의 대응 필요 |
| baseline의 의미 | 고정 ACE 소스를 **현재 OpenCode 스킬 프로필**에서 실행한 기준선 | 원본 runner를 연결·검증하기 전에는 native baseline이라고 부를 수 없음 |

`experiment.toml`은 `file_variants`로 `references/role-guidance.md`의 짧은 안내 후보를 만든다.
실환경 검증 후 주장할 수 있는 것은 선택한 데이터·모델·예산에서 **이 프로필의 안내 변경 효과**다.
스킬을 읽는 실행만으로 ACE-RTL 전체 알고리즘·native 역할 코드 최적화나 논문 재현을 주장할 수 없다.
현재는 실제 효과 자체도 미검증이다. 이 프로필은 초기 구현 선택이며 사용자 확정 요구사항이 아니다.

원본 baseline을 연결하려면 별도 Harness/wrapper, native Python·모델 의존성, OSS 평가 경로,
공개 입력/비공개 테스트 분리, 허용된 평가 피드백, timeout·정리·사용량 수집이 필요하다.
원본에 평가 루프가 있으므로 외부 evaluator와의 책임 분담·중복 평가도 결정해야 한다.
현재의 OpenCode 이미지와 CVDP 평가 이미지가 native 환경을 자동 제공하지 않는다.
대표 프로필 결정은 [다음 단계](NEXT_STEPS.md)의 선행 작업이다.

## CVDP 지원 경계

- setup은 고정 HF full no_commercial JSONL을 받아 302개 중 71개를 지원 형태로 변환하고
  231개 제외 사유를 기록한다. live는 QAM16 한 문제, evaluator-only smoke는 별도 고정 repo LFSR 예제다.
  `prepare.py:convert`는 `cid003`, 확인 가능한 `rtl/` 출력 대상, 검토한 OSS Compose/image 형태만 허용한다.
  coverage/PPA/agentic-heavy 등 전체 범주·평가 모드를 지원하지 않는다.
- CLI의 `no_commercial` 파일명 검사에 더해 harness 내용의 상용 도구 문자열과 이미지 조건을 검사한다.
  제외 목록은 `.excluded.json`에 기록한다. **정규식 검사는 전체 의존성 분석이 아니다.**
  과제 추가 시 실제 Compose/실행 명령·도구·채점 의미를 검토해야 한다.
- importer는 공개 input/context를 복사하고 reference output을 비운 뒤 private harness를 evaluation에 둔다.
  임의 신규 데이터의 input/context에 비공개 자료가 없는지까지 자동 판별하지는 않는다.
- evaluator는 후보 RTL을 `output.context`에 넣고 `run_benchmark.py -f ... -i ... -p ...`로 실행하도록 작성됐다.
  반환 tests가 비어 있지 않고 정수 result가 모두 0일 때 binary 통과다. 공식 score-based 집계의 대체물이 아니다.
- 알려진 환경 오류는 `infrastructure_error`, `passed=null`. `runner.py:GroupRunner.evaluate`는
  split 내 infrastructure_error/unsupported가 있으면 **해당 후보·split의 모든 집계 지표를 null**로 만든다.
  정상 trial만 남겨 성공률 분모를 줄이는 방식이 아니다. 모든 환경 오류 메시지의 포괄적 분류는 보장하지 않는다.
- 공식 `result=1, error_msg=null`도 실패한 test의 private log에서 Docker build/launch 오류를 확인한다.
  읽기 전 owned output prefix 내부 regular file인지 검증하며 로그 본문은 공개 feedback에 넣지 않는다.
  일반 HDL compile/기능 오답은 계속 `failed`, `passed=0`이다.
- `final_test=false`, 변환 과제는 모두 validation이다. 한 문제 smoke로 일반화 성능을 판단할 수 없다.

## 요구사항과 현재 구현 사이의 간극·후속 점검

| 근거 파일 | 현재 제한과 의미 |
|---|---|
| `config.py:load_experiment` | 모든 Agent가 모든 Harness adapter를 지원해야 한다. 호환성이 다른 대상들은 현재 별도 실험으로 나눈다. 임의 pair matrix 지원은 없음. |
| `workspace.py:CandidateStore.create`, `sources.py:_export_git` | 코드·설정도 텍스트로 수정할 수 있지만 삭제/바이너리 패치 API는 없다. symlink/submodule/LFS는 자동 처리하지 않으므로 대상에 따라 소스 준비 작업 필요. |
| `harnesses/opencode.py:run`, `runner.py:Context.record_usage` | OpenCode root step_finish의 input+output/cost만 `harness_reported_*` partial 지표. 전체 Agent 토큰/비용은 null. Optimizer usage는 플러그인의 명시적 보고 목록이며 빈 목록을 사용량 0으로 해석하지 않는다. |
| `config.py:budget`, `runner.py:Budget` | trial 수·시간·timeout만 지원. 비용 constraint는 평가 후 선택 제약이다. Optimizer 동기 호출 전후 시간 검사이지 내부 모델 호출을 선점 차단하는 기능이 아니다. |
| `runner.py:run_experiment`, `examples/ace-rtl/environment/setup.py` | source/benchmark/plugin/helper hash, HF hash, driver lock/설치 목록, 이미지 ID/도구 버전을 기록한다. dev의 Docker run은 ID, 공식 Dockerfile/Compose는 lock의 ID·platform과 대조한 로컬 tag를 사용한다. 이미지 내부 OS 저장소와 모델 서비스까지 완전히 고정하지 않는다. 직접 RTL 실행은 예제 안내대로 이미지 ID를 설정해야 한다. |
| `cli.py:main`, `runner.py:preflight` | plan의 integrations_ready는 registry/설정 및 evaluator별 사전검사 수준. Docker daemon·모델 인증·실제 결과 스키마까지 검증하지 않는다. 미구현 슬롯도 plan은 valid=true와 integrations_ready=false를 함께 출력할 수 있다. |
| `process.py`, `examples/ace-rtl/evaluator.py` | 코어 Agent 및 CVDP 정리는 별개다. 실제 CVDP timeout에서 전용 network의 컨테이너 제거와 별도 sentinel 보존을 확인했다. upstream의 초 단위 Compose project 이름은 외부 동시 실행 충돌 가능성이 있어 새 scheduler 보장으로 해석하지 않는다. |

현재의 논리적 평가 분리는 local 실행이나 신뢰한 in-process Optimizer에 대한 OS 보안 격리가 아니다.
공식 upstream pytest의 cache-permission warning과 cocotb deprecation은 checker를 변경하지 않고 기록한다.

## 검증 요약

- **전달 당시 기록:** Python 3.12, 32개 중 31개 통과·Icarus 1개 생략, uv 설치/최소 데모/ZIP 재실행/
  공개 CVDP 과제 변환 확인 보고. 이번에 그 환경·배포 ZIP을 재현한 것은 아니다.
- **현재 실제 실행:** macOS arm64 + uv Python 3.12.12, 공식 Docker ARM64 setup/offline/smoke 통과.
  패키징은 [Task 6 기록](verification.md#2026-09-20-task-6-cihandoffintegration), 최신 회귀·smoke 수치는 아래 최종 수정 기록을 따른다.
- **Ubuntu 실제 실행:** `10baa46`의 PR 코어 CI는 Python 3.11/3.12 각각 151개 중 150 통과·1 optional
  Docker config skip이며 native 실도구 9개를 포함한다. 수동 공식 run은 setup/offline/smoke와 별도
  실제 Docker config 검사까지 통과했다. [최종 native 재검증](verification.md#2026-09-20-native-ubuntu-repeat--passed)에 raw 정답/오답과 도구·이미지 근거를 기록한다.
- **미검증:** 실제 OpenCode→모델→CVDP end-to-end(API 키 부재), native ACE runner,
  전체 sub-agent 사용량, 실제 성능 개선. 개발 Harness 세션 자체는 제품 통합 검증이 아니다.

자세한 명령·산출물·검증 구분은 [verification.md](verification.md)에 기록한다.
