# Verilog-Eval 두 모드의 Ubuntu 전체 평가 검증 설계

## 목표와 주장 범위

사용자가 **`verilog-spec`와 `verilog-completion`을 모두 명시적으로 선택**했다. 고정 NVlabs/verilog-eval v2 `c498220d0a52248f8e3fdffe279075215bde2da6`의 각 모드 **156개, 합계 312개** 공개 과제를 실제 Ubuntu x86_64의 고정 Icarus v12 Docker 평가기로 검증한다. 이는 평가기·고정 자산의 reference 제출 정상 동작 검사다. 모델 Agent의 전체 문제 해결률이나 논문 재현 증거는 아니다.

## 선택과 실행

- `examples/benchmarks/verify_verilog_eval_full.py`는 인자로 정확히 하나의 `--dataset verilog-spec` 또는 `--dataset verilog-completion`을 받는다. 결과 JSON을 먼저 생성하고 사용자가 지정한 모드의 **기존 Dataset provider를 준비·진단**해 `tasks.json`·runtime lock·고정 source revision·Docker image ID/툴 버전을 확인한다. 준비 단계가 실패해도 `attempted=0`, `expected=156`, 확인 불가능한 ID 수와 환경 원인을 요약에 남긴다. source/tag/SHA를 갱신하거나 검증 없이 다른 이미지·모드로 바꾸지 않는다.
- 각 작업은 모든 task ID를 차례로 시도한다. 신뢰한 검증 스크립트만 동일 과제의 private `_ref.sv`를 읽어 **`module RefModule` 선언 한 곳만** 제출용 `module TopModule`로 변환한 후 기존 `VerilogEvaluator.evaluate(Task, output_dir, timeout_seconds=90)`에 전달한다. 과제별 결과는 공식 compiled/simulated verdict로 분류한다. private `_test.sv`, `_ref.sv`, 상세 simulator log는 Agent에 전달하거나 공개 artifact로 업로드하지 않는다. reference 코드의 구조가 지원 범위를 벗어나면 과제를 생략·합격 처리하지 않고 명시적 실패로 기록한다.
- 두 모드의 고정 `Prob001_zero`에서 `module TopModule(output zero); assign zero = 1'b1; endmodule`을 따로 제출해 **정상 컴파일 뒤 기능 불일치**로 실패하는 sanity를 확인한다. 각각의 기준 reference는 `output zero=0`이며 고정 `_ifc.txt`도 같은 인터페이스다. reference 156건이 모두 통과하고 이 오답 sanity가 실패/0인 경우에만 해당 모드가 통과한다. 한 건이라도 누락·환경 오류·채점 실패가 있으면 job은 실패한다.

## Ubuntu CI와 공개 증거

- `.github/workflows/ci.yml`에 수동 `workflow_dispatch.inputs.verilog_eval_full`(기본 false)과 **모드별 독립 job matrix**를 추가한다. `runs-on: ubuntu-24.04`에서 `uname -m=x86_64`·Docker `linux/amd64`를 확인하고, 사용자 선택 두 데이터셋을 각각 준비한다. 모드당 156개에 case 상한 90초, CI job 상한 330분을 둔다. PR에서는 전체 job을 실행하지 않고 API-free 계약 테스트만 수행한다. 병합·사용자 승인 뒤 `gh workflow run ci.yml --ref main -f verilog_eval_full=true`로 수동 실행한다.
- 각 job은 최종 **sanitized JSON**에 플랫폼·고정 Git revision·이미지 ID·공개 task 총수, 각 공개 ID/status/passed/경과·오류 범주와 완료 건수를 남긴다. 성공·실패 어느 쪽이든 시도된 과제와 못 시도한 과제를 구분해 artifact로 보존한다. 실패 사유는 정해진 값만 사용하고 private scorer/원시 로그·제출 reference·API 키는 artifact/문서에 넣지 않는다. 두 모드 점수를 하나로 합치거나 순위화하지 않는다.

## 검증 순서와 경계

1. 작은 모의 provider/평가기 fixture에서 전체 enumeration, 정상/오답/timeout/환경 장애, 한 건 실패 뒤에도 남은 과제 계속, 요약의 누락/비공개 필드 부재, 종료 코드를 TDD로 확인한다. 기존 `tests/test_verilog_live.py`의 단일 `verilog-spec` 실제 정답/오답도 준비한 Mac 환경에서 별도로 확인할 수 있지만 이를 Ubuntu 전체 실행으로 표시하지 않는다.
2. 선별적으로 Mac ARM64의 두 모드 pinned 준비·`Prob001_zero` 정답/오답을 검사해 CI verifier의 제출 형식과 경계를 확인한다. 이 검사는 Ubuntu native 근거가 아니다.
3. PR의 코어 회귀/문서 검사를 통과시키고 병합한 뒤 수동 Ubuntu matrix의 두 job/아티팩트·원시 workflow/run ID를 확인한다. 실제 결과만 `docs/verification.md`·`docs/status.md`·`docs/SOURCES.md`에 적는다. 실패하면 실패한 ID/환경 범위를 구분해 기록하고 다음 성공으로 대체하지 않는다. 공식 Verilog-Eval 상위 점수 집계, 실제 Agent/모델 실행, 최종 test 선택의 검증은 별개다.
