# 구현·검증 상태 (v0.3.0)

**Task 5 환경 검증 추가:** Mac Docker ARM64에서 고정 공식 OSS/OpenCode 이미지를 빌드하고
host-Docker toy 및 공식 CVDP 정답·오답 평가를 실행했다. 실제 동작에 맞게 print characterization을
수정한 뒤 T4 실제 도구 9/9 및 전체 smoke가 통과했다. 플랫폼 기본값은 Docker daemon native이며
live는 인증 부재로 미실행이다. 아래 기존 기준표의 실환경 미검증 항목은 이 추가 범위에 한해
[최신 검증 기록](verification.md)을 우선한다. 입력 제한은 필수이며 합성만으로 임의 RTL을 정화하지 않는다.

2026-09-20에 기준 commit `aeb732c0f1c138a568903c971baa17bfaa6b55e4`의 코드를 재확인했다.
이번 변경은 문서 보완이다. 요구사항은 [CONTEXT.md](CONTEXT.md), 외부 판단 근거는
[SOURCES.md](SOURCES.md), 실행 명령·환경·과거 기록은 [verification.md](verification.md)를 따른다.

## 현재 기능과 근거

아래 코어 경로는 `src/agent_optimizer/` 기준이다. **구현**은 코드 존재를,
**오프라인 검증**은 합성 실행/로컬 프로세스/모의 계약 테스트를 뜻하며 실환경 통합과 구별한다.

| 항목 | 코드 근거 | 현재 상태 |
|---|---|---|
| Python CLI·설정·플러그인 | `cli.py`, `config.py`, `registry.py`, `contracts.py` | 구현. 파일 플러그인/entry point 연결. 모든 Agent의 자동 호환을 보장하지 않음. |
| 로컬/Git 소스 스냅샷 | `sources.py` | 구현·로컬 임시 Git 테스트. Git full SHA 고정 및 원본 미수정. 실제 외부 ACE fetch 실행은 이번에 미검증. |
| 후보·editable·hash·diff·계보 | `workspace.py`, `runner.py:verify_candidate` | 구현·오프라인 검증. 텍스트 생성/교체, 경로 이탈·허용 밖 수정·변조 거부. |
| 독립 Agent × Harness | `config.py:load_experiment`, `runner.py:run_experiment` | 전체 조합, 순차 실행. 그룹별 후보/결과 분리, 오프라인 검증. 내부 sub-agent 자동 관리 기능은 아님. |
| baseline / file_variants | `optimizers/baseline.py`, `file_variants.py` | 실행 가능. 무변경 seed 반환 / 지정 파일 변형 열거. 연구 탐색 알고리즘이나 LLM 호출 없음. |
| 단계 조합·조건·선택 | `runner.py:GroupRunner.run`, `objectives.py` | 구현·오프라인 검증. 선행 stage 입력/validation gate, lexicographic·weighted·pareto 선택. |
| train / validation / test | `runner.py:Context`, `GroupRunner.run`, `config.py:load_tasks` | train-only 탐색 API, validation 선택, 선택 고정 후 선택적 test. family split 중복 거부. 최소 데모는 test까지 실행. |
| 결과·재현 자료 | `runner.py`, `results.py` | manifest, source-lock, 후보 diff/metadata, trial result/logs, events, frozen_selection, summary/report 저장. |
| command / OpenCode / Docker | `harnesses/command.py`, `harnesses/opencode.py`, `process.py` | 연결 코드 구현. argv·timeout 로컬 검증, OpenCode 이벤트/Docker는 모의 계약 검증. 프로젝트 어댑터를 통한 실제 통합은 미검증. |
| Icarus 예제 | `examples/rtl-debugger/{evaluator,iverilog}.py` | 연결 코드·모의 테스트. 실제 Icarus/vvp smoke는 미설치로 생략. |
| ACE 스킬 / CVDP | `examples/ace-rtl/` | setup/importer/어댑터/evaluator 포함. 실제 OpenCode·Docker·LLM·공식 시뮬레이션 통합 미검증. |
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

- `setup.sh`는 고정 CVDP repo의 비상용 공개 예제 파일을 사용한다. `prepare.py:convert`는
  `cid003` 포함, 명시적 `rtl/` 출력 대상, OSS placeholder를 쓰는 Dockerfile 등 초기 조건만 허용한다.
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
  정상 trial만 남겨 성공률 분모를 줄이는 방식이 아니다. 환경 오류 문자열 분류의 실환경 정확성은 미검증이다.
- `final_test=false`, 변환 과제는 모두 validation이다. 한 문제 smoke로 일반화 성능을 판단할 수 없다.

## 요구사항과 현재 구현 사이의 간극·후속 점검

| 근거 파일 | 현재 제한과 의미 |
|---|---|
| `config.py:load_experiment` | 모든 Agent가 모든 Harness adapter를 지원해야 한다. 호환성이 다른 대상들은 현재 별도 실험으로 나눈다. 임의 pair matrix 지원은 없음. |
| `workspace.py:CandidateStore.create`, `sources.py:_export_git` | 코드·설정도 텍스트로 수정할 수 있지만 삭제/바이너리 패치 API는 없다. symlink/submodule/LFS는 자동 처리하지 않으므로 대상에 따라 소스 준비 작업 필요. |
| `harnesses/opencode.py:run`, `runner.py:Context.record_usage` | OpenCode root step_finish의 input+output/cost만 `harness_reported_*` partial 지표. 전체 Agent 토큰/비용은 null. Optimizer usage는 플러그인의 명시적 보고 목록이며 빈 목록을 사용량 0으로 해석하지 않는다. |
| `config.py:budget`, `runner.py:Budget` | trial 수·시간·timeout만 지원. 비용 constraint는 평가 후 선택 제약이다. Optimizer 동기 호출 전후 시간 검사이지 내부 모델 호출을 선점 차단하는 기능이 아니다. |
| `runner.py:run_experiment`, `examples/ace-rtl/environment/setup.py` | 소스/benchmark/plugin hash 등은 남지만 모든 외부 환경을 자동 고정하지 않는다. OpenCode 이미지 `:local`은 가변이고 설치 entry point·모델 서비스의 버전 고정은 추가 기록 필요. |
| `cli.py:main`, `runner.py:preflight` | plan의 integrations_ready는 registry/설정 및 evaluator별 사전검사 수준. Docker daemon·모델 인증·실제 결과 스키마까지 검증하지 않는다. 미구현 슬롯도 plan은 valid=true와 integrations_ready=false를 함께 출력할 수 있다. |
| `process.py`, `examples/ace-rtl/evaluator.py` | 코어 Agent 컨테이너 정리와 CVDP가 생성한 평가 컨테이너 정리는 별개다. CVDP 프로세스 timeout 후 daemon 컨테이너 잔류 가능성은 실환경 점검 필요. |

현재의 논리적 평가 분리는 local 실행이나 신뢰한 in-process Optimizer에 대한 OS 보안 격리가 아니다.
위 항목은 문서로 확인한 한계이며 이번 작업에서 코드 동작을 변경하지 않았다.

## 검증 요약

- **전달 당시 기록:** Python 3.12, 32개 중 31개 통과·Icarus 1개 생략, uv 설치/최소 데모/ZIP 재실행/
  공개 CVDP 과제 변환 확인 보고. 이번에 그 환경·배포 ZIP을 재현한 것은 아니다.
- **이번 실제 실행:** macOS arm64, Python 3.14.5에서 31개 통과·Icarus 1개 생략.
  최소 합성 데모 Agent 2개·9 trial 완료, RTL plan 검증 및 GEPA plan 미구현 표시 확인.
- **미검증:** 프로젝트 어댑터를 통한 실제 OpenCode·Docker·LLM·CVDP 시뮬레이션, native runner,
  전체 sub-agent 사용량, 실제 성능 개선. 이 문서를 작성한 OpenCode 세션 자체는 제품 통합 검증이 아니다.

자세한 명령·산출물·검증 구분은 [verification.md](verification.md)에 기록한다.
