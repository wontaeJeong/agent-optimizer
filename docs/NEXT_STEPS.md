# 다음 개발 순서

## Agent 개발자: 실제 최적화 실행

1. `make setup ARGS="--core"` 후 `.venv/bin/agent-opt datasets list` 또는 `.venv/bin/agent-opt tui`에서
   CVDP/Verilog-Eval/사용자 JSON 데이터셋을 **직접 선택**한다. 다운로드·고정 해시·평가 도구 준비는
   선택 이후에 실행된다. 사용자 평가기는 별도 등록/검증이 필요하며 합성 점수로 바꾸지 않는다.
2. Agent의 고정 Git commit 또는 local 소스, 실제 CLI argv, prompt_file, editable 텍스트 범위를
   지정한다. 명시적인 harness/scaffold 파일이 없으면 Meta-Harness/Ecdysis를 선택할 수 없다.
   `.venv/bin/agent-opt doctor --plan runs/configs/<name>/experiment.toml --json`으로
   실행 전에 선언/등록·선택 자산을 읽기 전용 진단한다. `plan`은 실제 Agent 성공이 아니다.
3. 동일 모델/예산에서 GEPA·Meta-Harness·Ecdysis를 독립 stage로 실행하고 task/iteration 소요 시간을
   CLI/TUI에서 확인한다. 결과는 `report.html`의 validation 선택·frozen test·원본과 diff/partial usage로
   비교한다. 서로 다른 데이터셋을 지정했다면 session의 독립 보고서로 확인하고 점수를 합치지 않는다.
4. Mac Icarus v12 Verilog-Eval 정답/오답 실도구 검사, API-free fixture, DeepSeek→ACE 스킬 프로필→
   공식 CVDP 두 과제 E2E는 각각 다른 범위의 근거다. 다른 Agent·모델이나 연구 알고리즘의 성능을
   주장하기 전에는 실제 명령·모델·평가 결과를 [검증 기록](verification.md)에 추가한다.

## 팀 개발자: 새로운 컴포넌트 추가

1. **코어 준비:** `make setup ARGS="--core"` → `make doctor ARGS="--core"`.
   완료 기준: Docker/모델 없이 core ready와 첫 합성 보고서. 번호 메뉴 1/2도 같은 경로다.
2. **API-free fixture:** [Optimizer 계약 회귀](../experiments/optimizer-template/README.md)를 실행하고
   `make demo`의 두 Agent·한 repair stage·7 trial(solo 4/team 3)을 확인한다.
   완료 기준: 임시 테스트 결과와 지속 `runs/<run-id>/report.md` 구분, 합성 수치를 실제 성능으로 쓰지 않음.
3. **팀 플러그인 하나:** [역할 선택](../experiments/README.md) 후 팀 폴더에 구현하고
   `src/agent_optimizer/registry.py`에 ID/필요한 helper를 등록한다. `datasets list`, `doctor --dataset ID`, `doctor --plan PATH`로 점검한다.
   완료 기준: 파일 등록·실제 작은 실행·원본/editable 보존·명시적 오류·nullable usage.
   Optimizer는 train 피드백으로 수정하고 validation 수치로 후보를 선택한다. runner는 최종 test를 소유하며
   Harness는 argv/timeout/실제 산출물을 검증한다.
4. **독립 비교:** 필요하면 여러 Agent/Harness·파일 Optimizer를 같은 실험에 등록한다.
   각 stage는 baseline에서 시작하며 이력은 stage-local, 기본 최종 비교는 모든 winner다.
   완료 기준: 소스/평가/모델/예산 조건과 stage별 usage·diff·선택 근거를 보고서로 설명한다.
5. **선택적 ACE/모델:** [ACE 안내](../examples/ace-rtl/README.md)대로 전체 setup/doctor/smoke 후
   모델 자격증명을 준비해 `make doctor ARGS="--model"`, `make live ARGS="--iterations 3"`.
   완료 기준: 실제 OpenCode 산출물·공식 raw 결과·모델/예산/partial usage 기록. 실패를 다른 모델/fixture로 대체하지 않는다.

추가 연구 구현 채택 시 [고정 출처](SOURCES.md)를 확인한다. 실제 외부 Agent는 팀과 소스/권한/평가를 합의하고
customer template으로 연결한다. 한 문제 smoke는 일반화 성능 증거가 아니며 family 분리 비교가 별도로 필요하다.
현재 상태는 [status](status.md), 과거 증거는 [verification](verification.md), 보류 항목은 [FUTURE](FUTURE.md).
