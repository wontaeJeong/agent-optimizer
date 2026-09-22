# 다음 개발 순서

1. **코어 준비:** `make setup ARGS="--core"` → `make doctor ARGS="--core"`.
   완료 기준: Docker/모델 없이 core ready와 첫 합성 보고서. 번호 메뉴 1/2도 같은 경로다.
2. **API-free fixture:** [Optimizer 계약 회귀](../experiments/optimizer-template/README.md)를 실행하고
   `make demo`의 두 Agent·한 repair stage·7 trial(solo 4/team 3)을 확인한다.
   완료 기준: 임시 테스트 결과와 지속 `runs/<run-id>/report.md` 구분, 합성 수치를 실제 성능으로 쓰지 않음.
3. **팀 플러그인 하나:** [역할 선택](../experiments/README.md) 후 복사 경로를 고쳐 `plan`하고 구현한다.
   완료 기준: 파일 등록·실제 작은 실행·원본/editable 보존·명시적 오류·nullable usage.
   Optimizer는 train-only 탐색과 runner validation/test 소유권, Harness는 argv/timeout/실제 산출물을 검증한다.
4. **독립 비교:** 필요하면 여러 Agent/Harness·파일 Optimizer를 같은 실험에 등록한다.
   각 stage는 baseline에서 시작하며 이력은 stage-local, 기본 최종 비교는 모든 winner다.
   완료 기준: 소스/평가/모델/예산 조건과 stage별 usage·diff·선택 근거를 보고서로 설명한다.
5. **선택적 ACE/모델:** [ACE 안내](../examples/ace-rtl/README.md)대로 전체 setup/doctor/smoke 후
   모델 자격증명을 준비해 `make doctor ARGS="--model"`, `make live ARGS="--iterations 3"`.
   완료 기준: 실제 OpenCode 산출물·공식 raw 결과·모델/예산/partial usage 기록. 실패를 다른 모델/fixture로 대체하지 않는다.

연구 구현 채택 시 [고정 출처](SOURCES.md)를 확인한다. 실제 외부 Agent는 팀과 소스/권한/평가를 합의하고
customer template으로 연결한다. 한 문제 smoke는 일반화 성능 증거가 아니며 family 분리 비교가 별도로 필요하다.
현재 상태는 [status](status.md), 과거 증거는 [verification](verification.md), 보류 항목은 [FUTURE](FUTURE.md).
