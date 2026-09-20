# ACE-RTL 데모 연결

**기본 데모 대상은 외부 NVlabs/ACE-RTL입니다.** 원본 소스를 이 repo에 vendoring하지 않습니다.
source.toml이 고정 commit을 지정하고 실행 시 후보 스냅샷을 만듭니다.
setup은 별도로 `external/ACE-RTL`에 원본을 확보해 확인할 수 있게 합니다. 두 경로 모두 Git 제외입니다.

## 실행 프로필의 의미

현재 연결은 **OpenCode에서 ACE-RTL 스킬을 읽고 공개 RTL 과제를 수행하는 프로필**입니다.
ACE의 native runner / 자체 반복 루프 / 역할별 모델 호출과 동일하지 않습니다.
원본 전체 러너를 평가하려면 [upstream 실행 안내](https://github.com/NVlabs/ACE-RTL/blob/fead921f18bb57345b5a41ef93ba625be208e99c/README.md)를 따르고 별도 Harness 프로필을 연결하세요.
이 예제의 adapter.py에서 원본 스킬의 데이터셋 다운로드/자체 평가 지시를 외부 평가 방식에 맞게 제한합니다.
이는 v0.3.0의 초기 구현 선택이며 사용자가 원본 runner 대체를 확정한 것은 아닙니다.
역할 Python 파일의 실행 여부, 주장 가능한 최적화 범위, native baseline 연결 조건은
[상태 문서](../../docs/status.md#ace-rtl-실행-프로필), 고정 출처는 [SOURCES.md](../../docs/SOURCES.md)를 확인하세요.

## 준비

Python 3.11+ 진입점, uv, Git, 동작하는 Docker Engine/Compose가 필요합니다.
setup은 uv로 프로젝트 `.venv`와 별도 `external/cvdp-venv`를 Python 3.12로 준비합니다.
호스트에 simulator나 Python 패키지를 전역 설치하지 않습니다.

```bash
python3 scripts/dev.py setup                    # Docker daemon의 native 플랫폼 선택/기록
python3 scripts/dev.py smoke                    # 모델 키 없이 실제 도구/평가 확인
python3 scripts/dev.py setup --offline          # 검증된 소스/데이터/이미지/uv cache 재사용
# 명시적 플랫폼을 선택하는 경우 이후 명령에도 같은 값을 사용:
python3 scripts/dev.py setup --platform linux/arm64
python3 scripts/dev.py smoke --platform linux/arm64
# shell에 OPENROUTER_API_KEY와 사용 가능한 명시적 무료 모델을 설정한 뒤:
export AGENT_OPT_MODEL=openrouter/vendor/model:free
python3 scripts/dev.py live                     # 키가 없으면 blocked_auth
```

setup은 고정 버전 CVDP의 공식 Dockerfile.sim을 변경 없이 빌드하고 OpenCode 1.18.31 이미지를 별도로 만듭니다.
Icarus, Verilator, Yosys를 호스트에 각각 설치할 필요가 없습니다. OpenCode 컨테이너는 평가용 이미지와 별개입니다.
상용 EDA 이미지·라이선스는 제공하지 않습니다. setup 재실행 시 변경된 기존 checkout은 덮어쓰지 않습니다.
선택 플랫폼, 이미지 ID, 도구 버전, host driver 패키지 목록과 데이터 hash는
`external/environment-lock.json`, 실제 setup 로그와 doctor 결과는 `external/setup-logs/`에 남깁니다.
`doctor`는 이미지 존재 검사뿐 아니라 도구와 OpenCode를 실행합니다. `--offline`은
cache 누락/hash 불일치/이미지 ID 변경 시 실패하며 네트워크로 자동 보완하지 않습니다.
`--platform` 생략 시 호스트 CPU나 환경변수의 추정값 대신 Docker daemon의 OS/architecture를
조회합니다. 지원 범위는 `linux/amd64`, `linux/arm64`이며 명시적 override를 존중합니다.
빌드 실패 시 플랫폼을 바꾸는 자동 fallback은 없습니다. 주 대상인 Ubuntu x86_64는 별도 검증이 필요합니다.

`live`는 키가 없으면 `blocked_auth`, 무료 모델 형식이 아니면 `blocked_model`로 중단합니다.
실제 provider 오류도 실패로 남기며 유료 모델이나 합성 평가로 대체하지 않습니다.
이미지의 OpenCode 설정은 `{env:...}` 치환을 사용하며 main/small 모델 모두 선택한 무료 모델을 사용합니다.
호스트 credential store를 마운트하지 않고 키를 이미지나 설정 파일에 복사하지 않습니다.
일반 OpenAI-compatible 연결 예시는 `environment/openai-compatible.json`입니다.
`MODEL_BASE_URL`, `MODEL_ID`, `MODEL_API_KEY` 환경변수를 사용하며 무료 OpenRouter `live` 명령의 대체 경로는 아닙니다.
설정은 새 OpenCode 컨테이너가 시작할 때 적용됩니다.

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
기본 live 실험용 `tasks.json`에는 명시적으로 선택한 `cvdp_copilot_16qam_mapper_0001`만 넣습니다.
공식 LFSR smoke는 별도의 고정 repo 예제입니다. HF 전체 파일의 LFSR은 `cid004`인
`lfsr_0007`뿐이므로 live 과제로 대체하거나 지원 범위를 넓히지 않습니다.

`smoke`는 T4 실제 도구 테스트 9개(skip 금지), **호스트 evaluator의 Docker runtime**을 통한
toy RTL 정답/오답/조기 종료, 공식 LFSR 정답/오답 제출을 확인합니다.
정답은 고정 CVDP repo의 reviewed reference를 trusted evaluator에서만 사용합니다.
공식 성공 판정에는 비어 있지 않은 raw tests가 필요합니다. 산출물은 `runs/dev-smoke-*/`에 남습니다.

실제 test 결과가 있는 raw_result.json만 파싱합니다. 알려진 환경 실패는 `passed=null`로 반환하며,
코어는 해당 후보·split 집계 전체를 무효화합니다. 정상 trial만으로 성공률을 재계산하는 방식이 아닙니다.
초기 범위는 cid003 기능 검증/rtl 출력입니다. coverage/PPA/agentic-heavy 등은 지원하지 않고 제외합니다.
상용 도구 문자열·비공식 base image가 발견되어도 제외 보고서에 기록합니다. 범위를 넓힐 때는
공식 harness 의존성과 채점 의미를 검토하고 importer/evaluator 테스트를 갱신하세요.

## 최적화

experiment.toml은 원본과 짧은 role-guidance 후보를 비교합니다. 알고리즘은 실제 연구 optimizer가 아닌
file_variants입니다. 팀원이 GEPA 등 구현을 연결하면 같은 source/evaluator를 사용합니다.
이 한 문제는 validation-only smoke이므로 일반화 성능 근거가 아닙니다. 본 실험은 서로 다른 family의
train/validation/test 과제를 준비하고 호출·시간 예산 및 모델을 맞추세요.

기본 timeout은 OpenCode + CVDP 평가 합산입니다. 첫 Docker 빌드는 setup에서 완료해야 합니다.
토큰 전체 합산은 미지원이며 partial 지표만 관측됩니다. API 응답/trace에는 민감정보가 있을 수 있으므로
runs를 Git에 추가하지 마세요.

## 현재 검증 범위

과제 공개/비공개 분리와 공식 결과 형식 처리는 오프라인 테스트합니다.
플랫폼별 실제 실행 결과와 차단 사유는 [검증 기록](../../docs/verification.md)을 확인하세요.
source/evaluator 버전이 바뀌면 한 문제로 입출력과 보고서 형식을 먼저 검증하세요.

외부 CVDP 프로세스 종료 시 해당 trial의 고유 network에 연결된 컨테이너만 정리합니다.
정리 결과는 private evaluator의 `logs/cleanup.json`에 남습니다. 자동 resume은 지원하지 않습니다.
