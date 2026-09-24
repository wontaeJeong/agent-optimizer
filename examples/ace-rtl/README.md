# ACE-RTL 데모 연결

**기본 데모 대상은 외부 NVlabs/ACE-RTL입니다.** 원본 소스를 이 repo에 vendoring하지 않습니다.
source.toml이 고정 commit을 지정하고 실행 시 후보 스냅샷을 만듭니다.
setup은 별도로 `external/ACE-RTL`에 원본을 확보해 확인할 수 있게 합니다. 두 경로 모두 Git 제외입니다.

## 실행 프로필의 의미

현재 연결은 **OpenCode에서 ACE-RTL 스킬을 읽고 공개 RTL 과제를 수행하는 프로필**입니다.
ACE의 native runner / 자체 반복 루프 / 역할별 모델 호출과 동일하지 않습니다.
원본 전체 러너를 평가하려면 [upstream 실행 안내](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/README.md)를 따르고 별도 Harness 프로필을 연결하세요.
이 예제의 adapter.py에서 원본 스킬의 데이터셋 다운로드/자체 평가 지시를 외부 평가 방식에 맞게 제한합니다.
이번 반복 최적화 데모는 이 스킬 프로필을 사용합니다. 원본 ACE 전체 알고리즘 최적화라는 주장은 하지 않습니다.
역할 Python 파일의 실행 여부, 주장 가능한 최적화 범위, native baseline 연결 조건은
[상태 문서](../../docs/status.md#ace-rtl-실행-프로필), 고정 출처는 [SOURCES.md](../../docs/SOURCES.md)를 확인하세요.

## 준비

Python 3.11+ 진입점, uv, Git, 동작하는 Docker Engine/Compose가 필요합니다. CA 포함 빌드는 Buildx가 필요합니다.
setup은 uv로 프로젝트 `.venv`와 별도 `external/cvdp-venv`를 Python 3.12로 준비합니다.
호스트에 simulator나 Python 패키지를 전역 설치하지 않습니다.
기존 driver 환경도 online/offline setup과 doctor에서 실제 interpreter의 major/minor를 확인합니다.
Python 3.12가 아니면 환경을 보존한 채 중단합니다. 필요한 파일을 보관하고 해당 환경 디렉터리를
직접 다른 위치로 옮긴 뒤 setup을 다시 실행하면 uv가 Python 3.12 환경을 생성합니다.

driver 의존성은 [requirements-cvdp-py312.txt](environment/requirements-cvdp-py312.txt)의
universal uv-compiled 전이 pin으로 `uv pip sync`합니다. 고정 upstream requirements는 변경하지 않으며
입력 hash를 검증합니다. compiled lock hash와 실제 설치 목록은 환경 lock에 저장합니다.
offline setup 및 doctor/smoke/live는 lock/설치 목록 drift를 거부하므로 예전 환경은 한 번 online setup을
실행하세요. Python lock은 공식 이미지 내부의 OS/도구 패키지까지 고정하지 않습니다.

```bash
python3 scripts/dev.py setup                    # Docker daemon의 native 플랫폼 선택/기록
python3 scripts/dev.py doctor                   # 모델 호출 없이 환경 검사
python3 scripts/dev.py smoke                    # 모델 키 없이 실제 도구/평가 확인
python3 scripts/dev.py setup --offline          # 검증된 소스/데이터/이미지/uv cache 재사용
# 명시적 플랫폼을 선택하는 경우 이후 명령에도 같은 값을 사용:
python3 scripts/dev.py setup --platform linux/arm64
python3 scripts/dev.py smoke --platform linux/arm64
# 실제 endpoint와 AGENT_OPT_MODEL_API_KEY를 셸에 설정한 뒤:
export AGENT_OPT_MODEL_ENDPOINT=https://model.example/v1/chat/completion
export AGENT_OPT_MODEL_ID=glm5.3-flash
python3 scripts/dev.py doctor --model           # 호스트 API + 컨테이너 OpenCode 실제 도구 호출
python3 scripts/dev.py live --iterations 3      # 기본 3회 수정; 1..20 범위
```

setup은 고정 버전 CVDP의 공식 Dockerfile.sim을 변경 없이 빌드하고 OpenCode 1.18.31 이미지를 별도로 만듭니다.
Icarus, Verilator, Yosys를 호스트에 각각 설치할 필요가 없습니다. OpenCode 컨테이너는 평가용 이미지와 별개입니다.
상용 EDA 이미지·라이선스는 제공하지 않습니다. setup 재실행 시 변경된 기존 checkout은 덮어쓰지 않습니다.
선택 플랫폼, 이미지 ID, 도구 버전, host driver 패키지 목록과 데이터 hash는
`external/environment-lock.json`, 실제 setup 로그와 doctor 결과는 `external/setup-logs/`에 남깁니다.
`doctor`는 이미지 존재 검사뿐 아니라 도구와 OpenCode를 실행합니다. `--offline`은
cache 누락/hash 불일치/이미지 ID 변경 시 실패하며 네트워크로 자동 보완하지 않습니다.
`doctor/smoke/live`는 평가 이미지 tag의 로컬 ID/platform을 lock과 대조합니다. 공식 driver의
`OSS_SIM_IMAGE`에는 검증된 tag를 전달합니다. bare `sha256:<local image ID>`는 Dockerfile FROM에서
registry 이름으로 해석될 수 있으므로 사용하지 않습니다. Docker run에는 계속 locked ID를 사용합니다.
`--platform` 생략 시 호스트 CPU나 환경변수의 추정값 대신 Docker daemon의 OS/architecture를
조회합니다. 지원 범위는 `linux/amd64`, `linux/arm64`이며 명시적 override를 존중합니다.
빌드 실패 시 플랫폼을 바꾸는 자동 fallback은 없습니다. `10baa46`의 native Ubuntu x86_64
setup/offline/smoke·provider config 재검증은 통과했습니다. 첫 FROM 참조 실패와 수정 후 정답·오답
근거는 [최종 검증 기록](../../docs/verification.md#2026-09-20-native-ubuntu-repeat--passed)에 보존합니다.

`AGENT_OPT_MODEL_ENDPOINT`는 완전한 completion URL을 그대로 사용합니다. 표준 경로이면 대신
`AGENT_OPT_MODEL_BASE_URL`을 지정하고 `/chat/completions`를 붙입니다. 둘을 동시에 지정하면 오류입니다.
`AGENT_OPT_MODEL_API_KEY`는 Bearer 토큰, `AGENT_OPT_MODEL_ID`는 기본 `glm5.3-flash`를 덮어씁니다.
`live`는 main/small 모델을 모두 `compatible/<AGENT_OPT_MODEL_ID>`로 설정합니다. API 오류는 중단하며 대체 모델을 호출하지 않습니다.
이미지의 `compatible.json`과 dependency-free endpoint plugin이 스트리밍/도구 호출을 유지하며 URL만 연결합니다.
호스트 credential store를 마운트하거나 토큰을 이미지에 복사하지 않습니다.
설정은 새 OpenCode 컨테이너 시작 시 적용됩니다. 별도로 실행 중인 OpenCode는 종료 후 다시 시작해야 합니다.
`doctor --model`은 실제 모델 호출을 수행합니다. 일반 `doctor` 통과만으로 API 연결 성공을 주장하지 않습니다.

## 평가

데이터는 Hugging Face revision `5b807d945f6a99aa645f7e43a64a2115e281b4bf`의
`cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl`입니다.
LICENSE/NOTICE도 같은 revision에서 정확한 파일만 HTTPS로 내려받고, 검토 후 고정한 SHA-256을 검증합니다.
기대 hash의 출처는 [SOURCES.md](../../docs/SOURCES.md)에 기록합니다.
`prepare.py`가 input/context와 출력 대상
경로만 공개 과제로 만들고, private harness는 evaluation에만 보관합니다. reference output은 지웁니다.
Agent 컨테이너에는 과제와 ACE 후보 소스만 마운트합니다.
`evaluator.py`는 산출 RTL을 official row의 output.context에 넣고 공식 `run_benchmark.py`로 재평가합니다.
여기서 upstream golden 모드는 **제출한 후보 RTL 평가**에 사용되며 정답을 Agent에 제공하지 않습니다.
정답 본문이 없는 공식 데이터도 명시적 output/context 경로를 사용하고, 경로가 없으면 검토한
private `src/.env`의 literal `VERILOG_SOURCES=/code/rtl/...`에서만 추출합니다. 경로를 추측하지 않습니다.
전체 지원 과제는 `datasets/ace-demo/all-tasks.json`, 제외 사유는 `.excluded.json`에 저장합니다.
기본 live `tasks.json`은 `cvdp_copilot_8x3_priority_encoder_0001`(train)과
`cvdp_copilot_16qam_mapper_0001`(validation)을 사용합니다. 서로 다른 문제 family이며 test는 설정하지 않습니다.
공식 LFSR smoke는 별도의 고정 repo 예제입니다. HF 전체 파일의 LFSR은 `cid004`인
`lfsr_0007`뿐이므로 live 과제로 대체하거나 지원 범위를 넓히지 않습니다.

`smoke`는 T4 실제 도구 테스트 9개(skip 금지), **호스트 evaluator의 Docker runtime**을 통한
toy RTL 정답/오답/조기 종료, 공식 LFSR 정답/오답 제출을 확인합니다.
정답은 고정 CVDP repo의 reviewed reference를 trusted evaluator에서만 사용합니다.
공식 성공 판정에는 비어 있지 않은 raw tests가 필요합니다. 산출물은 `runs/dev-smoke-*/`에 남습니다.
공식 checker의 pytest cache-permission warning(`/rundir/harness/.cache`)과 cocotb deprecation은
현재 비치명적이다. 정답/기능 오답 모두 실제 검사 결과를 확인했고 upstream checker/Compose는 수정하지 않았다.

실제 test 결과가 있는 raw_result.json만 파싱합니다. 알려진 환경 실패는 `passed=null`로 반환하며,
코어는 해당 후보·split 집계 전체를 무효화합니다. 정상 trial만으로 성공률을 재계산하는 방식이 아닙니다.
`result=1, error_msg=null`일 때도 owned output prefix 내부의 검증된 private log로 Docker build/launch
오류를 구분합니다. 공개 feedback에 로그 내용을 넣지 않으며 일반 HDL compile/기능 실패는 0점입니다.
초기 범위는 cid003 기능 검증/rtl 출력입니다. coverage/PPA/agentic-heavy 등은 지원하지 않고 제외합니다.
상용 도구 문자열·비공식 base image가 발견되어도 제외 보고서에 기록합니다. 범위를 넓힐 때는
공식 harness 의존성과 채점 의미를 검토하고 importer/evaluator 테스트를 갱신하세요.

## 최적화

experiment.toml은 [단순 feedback Optimizer](../../experiments/simple-feedback/README.md)를 파일 플러그인으로 등록합니다.
원본 train 평가 → LLM이 role-guidance 수정 → train 재평가를 기본 3회 수행합니다.
adapter가 지침 내용을 prompt에 직접 포함하므로 변경이 실제 Harness 입력에 반영됩니다.
runner는 원본과 세 후보를 validation으로 비교합니다. 기본 8 trial, trial당 최대 600초이며 실제 소요 시간은 모델/과제에 따릅니다.
`--iterations`는 반복 횟수와 그에 맞는 trial/시간 예산을 조정합니다. `runs/dev-live/<id>/report.md`에서
baseline·선택 결과·Optimizer usage를, 후보별 `changes.diff`에서 변경을 확인합니다.
연구 알고리즘은 팀 플러그인으로 교체합니다. 작은 train/validation 데모는 일반화 성능 근거가 아닙니다.

기본 timeout은 OpenCode + CVDP 평가 합산입니다. 첫 Docker 빌드는 setup에서 완료해야 합니다.
토큰 전체 합산은 미지원이며 partial 지표만 관측됩니다. API 응답/trace에는 민감정보가 있을 수 있으므로
runs를 Git에 추가하지 마세요.

## 현재 검증 범위

과제 공개/비공개 분리와 공식 결과 형식 처리는 오프라인 테스트합니다.
Mac Docker ARM64와 native Ubuntu x86_64에서 evaluator-only 정답/오답을 확인했습니다.
API 키 부재로 live는 여전히 `blocked_auth`이며 실제 ACE/OpenCode→모델→CVDP 결과는 미검증입니다.
플랫폼별 실제 실행 결과와 차단 사유는 [검증 기록](../../docs/verification.md)을 확인하세요.
source/evaluator 버전이 바뀌면 한 문제로 입출력과 보고서 형식을 먼저 검증하세요.
수동 공식 CI는 [기존 ci.yml 입력](../../CONTRIBUTING.md#ci와-pr-병합)으로 같은 public 명령을 실행합니다.

외부 CVDP 프로세스 종료 시 해당 trial의 고유 network에 연결된 컨테이너만 정리합니다.
정리 결과는 private evaluator의 `logs/cleanup.json`에 남습니다. 자동 resume은 지원하지 않습니다.
