# 다음 개발 순서

요구사항은 [CONTEXT.md](CONTEXT.md), 출처·버전은 [SOURCES.md](SOURCES.md), 현재 제한은
[status.md](status.md)를 먼저 확인한다. 한 경로를 끝까지 검증한 뒤 확장한다.

1. **대상 Linux 서버에서 최소 데모 재검증**
   - `AGENTS.md`의 unittest와 minimal 실행 명령을 사용한다. 이번 macOS 결과는
     [verification.md](verification.md)에 있으며 Linux 준비 완료를 뜻하지 않는다.
   - 완료 기준: 독립 Agent 2개·9 trial의 합성 실행, baseline/후보 결과, manifest/diff/선택 고정 파일 확인.
     실패·skip·Python 버전을 기록하고 0→1을 실제 Agent 성능 수치로 사용하지 않는다.
2. **대표 ACE 실행 프로필 결정 및 upstream 차이 확인**
   - 스킬 프로필 또는 원본 runner 중 데모에서 평가할 대상을 정하고, 변경 파일이 실제 읽히거나
     실행되는 경로를 확인한다. native 선택 시 별도 어댑터, 의존성, 역할별 모델/반복 예산,
     제한된 평가 피드백 경계를 먼저 설계한다.
   - 완료 기준: 고정 SHA 기준 실행 명령·호출 흐름·원본과의 차이·baseline 정의·주장 가능한 개선 범위를
     ACE 예제 문서에 기록. 역할 Python 코드 최적화 주장에는 실제 호출 근거가 있어야 한다.
3. **공식 OSS CVDP 한 문제 실환경 검증**
   - Agent/Harness 이미지와 CVDP 평가 이미지를 별도로 준비한다. 선택한 OpenCode/모델과 환경을
     고정하고 과제의 실제 OSS 의존성을 검토한다. `plan` 이후 실제 제출 RTL을 외부 evaluator로 평가한다.
   - 완료 기준: 공개/비공개 입력 분리, 후보 RTL 제출, 비어 있지 않은 공식 raw_result와 pass/fail/환경 오류
     분류, 실행 로그·이미지/소스 버전·제외 사유 보존. Agent 자기보고나 `plan`만으로 완료 처리하지 않는다.
4. **대표 연구 Optimizer 하나 연결**
   - 담당자가 [출처 후보](SOURCES.md#연구-optimizer-출처-후보-조사와-채택-확정을-구분)를 확인하고
     정확한 구현·버전을 선택한다. 기존 계약과 파일 플러그인 연결을 우선 사용한다.
   - 완료 기준: 원본 보존·editable 준수, train-only 탐색, validation 선택, Optimizer 사용량 별도 기록,
     실패 시 명시적 오류를 관련 테스트와 작은 실행으로 확인. 전체 알고리즘 동시 구현은 하지 않는다.
5. **공정한 baseline/후보 비교**
   - 동일 소스 기준, Harness·모델·평가 버전·데이터·반복 조건·예산으로 비교한다.
     family가 겹치지 않는 train/validation/test를 준비하고 test는 선택 고정 후 실행한다.
   - 완료 기준: 성공률과 관측 가능한 시간/토큰/비용, 전체·partial 사용량 구분, Optimizer 비용,
     환경 오류, diff와 재실행 정보를 포함한 보고서. 한 문제 smoke와 일반화 성능을 구별한다.
6. **다른 팀 Agent 하나로 범용성 확인**
   - 해당 팀과 소스 버전·실행법·수정 권한·평가법을 확정하고 `experiments/customer-template/`에서 시작한다.
     필요한 어댑터를 만들되 코어에 고객별 분기를 추가하지 않는다.
   - 완료 기준: 독립 Agent로 baseline과 후보를 실행하고 버전·계보·결과를 분리해 기록한다.
     ACE 전용 코드 없이 같은 계약을 사용함을 확인하고 추가 연결 작업도 문서화한다.
