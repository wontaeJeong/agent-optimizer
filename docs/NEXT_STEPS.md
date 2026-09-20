# 다음 개발 순서

요구사항은 [CONTEXT.md](CONTEXT.md), 출처·버전은 [SOURCES.md](SOURCES.md), 현재 제한은
[status.md](status.md)를 먼저 확인한다. 한 경로를 끝까지 검증한 뒤 확장한다.

1. **native Ubuntu x86_64 CI와 공식 Docker 통합 실행**
   - 코어 Python 3.11/3.12 CI는 native apt Yosys/Icarus까지 검사한다. 브랜치가 원격에 올라간 뒤
     `gh workflow run ci.yml --ref feat/mvp-hardening -f official_cvdp=true`로 공식 setup/offline/smoke를 실행한다.
   - 완료 기준: 코어·wheel 및 공식 정답/오답 raw 결과, 이미지/driver lock hash와 도구 버전 보존.
     현재 [Mac Docker ARM64 결과](verification.md)는 Ubuntu 실행을 대신하지 않는다.
2. **대표 ACE 실행 프로필 결정 및 upstream 차이 확인**
   - 스킬 프로필 또는 원본 runner 중 데모에서 평가할 대상을 정하고, 변경 파일이 실제 읽히거나
     실행되는 경로를 확인한다. native 선택 시 별도 어댑터, 의존성, 역할별 모델/반복 예산,
     제한된 평가 피드백 경계를 먼저 설계한다.
   - 완료 기준: 고정 SHA 기준 실행 명령·호출 흐름·원본과의 차이·baseline 정의·주장 가능한 개선 범위를
     ACE 예제 문서에 기록. 역할 Python 코드 최적화 주장에는 실제 호출 근거가 있어야 한다.
3. **무료 모델 live 한 문제 실행**
   - evaluator-only 공식 LFSR 정답/오답 smoke는 Mac Docker ARM64에서 통과했다. 다음은
     `OPENROUTER_API_KEY`와 사용 가능한 명시적 `openrouter/vendor/model:free`를 환경에 설정하고
     `python3 scripts/dev.py live`로 full HF의 QAM16 한 문제를 실행하는 것이다.
   - 완료 기준: 실제 OpenCode 산출물 → 비어 있지 않은 공식 raw 결과, 모델/예산/partial 사용량 기록.
     인증·무료 모델 가용성 실패는 차단으로 남기고 유료 모델·합성 결과로 대체하지 않는다.
4. **대표 연구 Optimizer 하나 연결**
   - 담당자가 [출처 후보](SOURCES.md#연구-optimizer-출처-후보-조사와-채택-확정을-구분)를 확인하고
     정확한 구현·버전을 선택한다. 기존 계약과 파일 플러그인 연결을 우선 사용한다.
     `experiments/optimizer-template/`과 `tests/test_plugin_contracts.py`를 시작점으로 사용한다.
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
