# 검증 순서

**코어 배선 검사 → 팀 fixture → 실제 Agent/평가 환경** 순으로 확인합니다. 아래 명령은 저장소 루트에서 실행합니다. plan·stub·합성 검사 성공을 외부 모델 실행 성공으로 취급하지 마세요.

## 1. 코어와 계약

```bash
make setup-core
make doctor-core
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml
```

계약 테스트는 원본 보존·후보 범위·그룹별 독립 실행·선택 경계를 API-free fixture로 검증합니다. 최소 예제의 7 trial은 실제 모델·외부 채점 환경이 아닌 **합성 결과**입니다.

## 2. 팀 파일과 선언

예를 들어 `experiments/my-team/`에 복사한 팀 템플릿의 참조를 고친 뒤:

```bash
PYTHONPATH=src .venv/bin/python -m agent_optimizer plan experiments/my-team/experiment.toml
.venv/bin/agent-opt datasets list
.venv/bin/agent-opt doctor --plan experiments/my-team/experiment.toml --json
```

템플릿 종류에 따라 준비한 `experiment.toml`의 자산·provider 등록 조건은 다릅니다. `plan`/`doctor --plan`은 선언, 플러그인 파일과 선택 자산의 **정적 점검**입니다. 원본 stub의 의도된 실패 또는 외부 환경 누락은 실제 구현으로 해결하며 baseline/합성 평가로 대체하지 않습니다.

## 3. 선택한 자산과 실제 실행

새 Dataset을 등록했다면 사용자 선택 후에만 `.venv/bin/agent-opt doctor --dataset team_dataset --json`으로 준비 상태를 읽기 전용 진단합니다. 통과한 뒤 작은 공개 train/validation 과제로 팀의 `run`을 실행하고, 실제 Agent 산출물·Evaluator 근거·`runs/<run-id>/report.html`의 상태/사용량을 함께 확인하세요.

```bash
PYTHONPATH=src .venv/bin/python -m agent_optimizer run experiments/my-team/experiment.toml
make lint
make test
git diff --check
```

실제 외부 모델·Harness·평가기를 쓸 때는 별도 자격증명과 평가 환경을 준비하고 작은 실행부터 확인합니다. 실패한 도구 실행을 성공으로 대체하지 말고, 사용한 소스 commit·데이터셋 버전·모델·예산·평가기를 기록하세요. [구조와 경계](overview.md)를 따라 train 피드백과 선택 후 test의 구분도 확인합니다.

## 4. ACE/CVDP 실행환경과 모델 검증

코어 계약 테스트와 별도로 실제 Docker 자산·공식 채점기를 준비합니다. 저장소의 수동
`official_cvdp=true` CI는 모델 자격증명 없이 공식 정답/오답과 ACE CLI의 인증 실패 경로를
확인하며, 모델을 사용하는 live 성공은 뜻하지 않습니다.

```bash
make setup
make doctor
make smoke
# 모델 자격증명과 endpoint를 환경에서 지정한 뒤:
sh scripts/bootstrap.sh doctor --model
.venv/bin/agent-opt run examples/ace-rtl/experiment.toml
```

마지막 명령은 ACE 스킬 프로필을 기존 `live` 경로로 실행합니다. 같은 고정 프로필은
`.venv/bin/agent-opt tui`의 **기존 실험 실행**에서도 고를 수 있습니다. 공식 raw 결과와
`runs/dev-live/<run-id>/summary.json`·`report.html`을 확인하고 미실행/차단을 따로 기록하세요.
