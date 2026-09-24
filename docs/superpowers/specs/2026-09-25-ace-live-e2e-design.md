# ACE-RTL 실제 모델 E2E 검증 설계

## 목표와 판정

기존 ACE-RTL OpenCode 스킬 프로필의 **실제 모델 API → Agent 컨테이너 → 공개 과제 산출물 → 호스트의 공식 CVDP 평가 → Optimizer 후보 선택 → 보고서** 흐름을 이번 작업 환경에서 확인한다. `make setup`으로 고정 소스·데이터·이미지를 준비하고 `make doctor`, `make smoke`, `make doctor ARGS="--model"`, `make live ARGS="--iterations 1"`을 순서대로 실행한다. 최종 성공 판정은 준비 진단, 실제 모델 도구 호출, 공식 평가의 정답·오답 smoke, live 완료 상태, 원본/후보와 validation 평가 근거 및 `report.html`의 존재를 함께 확인한다. 실제 개선 점수는 측정값 그대로 기록하며 향상을 성공 조건으로 만들지 않는다.

## 선택한 접근과 경계

- 기존 `scripts/dev.py`와 `examples/ace-rtl/environment/{setup,model_checks,checks}.py` 경로를 재사용한다. `live --iterations 1`은 준비한 train/validation 각각에 baseline·후보를 실행하는 4-trial 상한이다. Agent의 공개 입력과 CVDP의 private 평가 자료 분리를 유지한다.
- 모델은 OpenAI 호환 `MODEL_BASE_URL=https://api.deepseek.com`, `MODEL_ID=deepseek-flash`로 연결한다. `/anthropic` 경로는 현재 OpenAI 호환 클라이언트 계약과 다르다. 인증정보는 실행 중 환경/credential store에서만 읽고 저장소 설정·문서·커밋·PR·검증 기록에 남기지 않는다. API 요청과 도구 실행은 제한된 trial/시간 예산을 따른다.
- `doctor --model`은 모델의 호스트 tool-call과 컨테이너 OpenCode 도구 실행을 확인한다. `smoke`는 모델 없이 실제 도구 및 공식 CVDP 정답·오답 평가를 확인한다. `live`의 성공/실패와 각 단계의 원시 결과·이벤트를 별도로 판정해 합성 fixture나 mock 응답을 실제 모델 실행으로 기록하지 않는다.

## 오류 처리·변경 범위

각 단계를 실행하기 전에 현재 환경 상태를 확인하고 실패를 재현한다. 2026-09-25 CI에서 관측된 upstream `apt` 저장소 404는 이번 환경에서도 발생하는지 먼저 확인한다. Docker/네트워크/이미지/모델·응답 형식/평가/보고서 오류는 단계별 로그로 원인을 좁히고, 재현된 프로젝트 소유 문제만 최소 수정한다. 고정 외부 SHA나 upstream 평가 기준을 통과 목적으로 갱신·변조하지 않는다. 외부 저장소 장애 또는 인증 제한이 재현되면 그 상태와 이미 확인한 단계까지를 구분해 보고한다.

수정 시 관련 회귀를 먼저 추가하고 코어 계약·소스/데이터 격리·오류 상태를 유지한다. 변경 후 관련 회귀, `make lint`, `make test`, 최소 데모 및 위 실환경 순서를 다시 확인하고 실제 명령·환경·결과를 `docs/verification.md`에 날짜별로 남긴다. 실제 모델 경로가 막혔을 때만 기존 로컬 HTTP fixture 기반 연결 검사를 별도로 실행할 수 있으며 그 결과는 실제 모델 E2E 완료로 표시하지 않는다.

## 고려한 대안

- 단일 Docker sidecar mock API: 호스트와 OpenCode 양쪽에 같은 응답을 공급할 수 있지만 모델 추론 자체는 확인하지 못하고 Docker 네트워크·fixture 코드를 추가해야 한다.
- Agent/Harness·평가를 대체하는 합성 fixture: 가장 빠르지만 이미 검증된 코어 경로에 가까워 이번 목표인 공식 평가 연결의 근거가 되지 않는다.

실제 모델 접속 정보가 제공되었으므로 우선 기존 실환경 경로를 선택한다. 실패가 발생하면 단계별 차단 사유와 실제로 검증한 범위만 주장한다.
