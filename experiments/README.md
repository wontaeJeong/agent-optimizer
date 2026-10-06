# 담당별 시작점

팀 구현은 **`experiments/<team>/`**에서 소유하고 Dataset/Harness/Optimizer/Evaluator ID를
`src/agent_optimizer/registry.py`의 `PROJECT_COMPONENTS`에 등록하면 CLI/TUI·doctor 목록에서 탐색할 수 있습니다.
프로젝트 루트에서 복사하고 선택한 README의 post-copy 경로를 바꾼 뒤 `plan`으로 배선을 확인하세요.
필요한 helper 경로는 `PROJECT_DEPENDENCIES`에 선언하고 CLI 선택지·entry-point 패키지 설치는 바꾸지 않습니다.

새 `init`은 기본 `~/.agent-optimizer/experiments/<이름>-<uuid12>/experiment.toml`에 생성한다. JSON `experiment`를 정본으로 사용하고 원본 project_root provenance·config_root·output **부모**를 구별한다. legacy 자료는 자동 이동하지 않는다. 상세는 [구조/경계](../docs/architecture.md)다. 도메인 native 정책은 `examples/ace-rtl/` 소유이며 core thin hook·공통 계약으로 연결한다. [native 조건/표면](../examples/ace-rtl/NATIVE.md)의 fixture 검증과 실모델/EDA not_run을 구분한다.

| 담당 | 복사할 템플릿 | 첫 완료 조건 |
|---|---|---|
| Optimizer | [optimizer-template](optimizer-template/README.md) | API-free 계약 테스트 → propose/evaluate 구현 → validation 선택 |
| Harness | [harness-template](harness-template/README.md) | Agent/프로필/등록 경로 연결 → 실제 CLI 실행·오류/사용량 검증 |
| Dataset | [dataset-template](dataset-template/README.md) | 공개 task/분할·private 평가 자료·검증된 출처/해시·평가기 연결 |
| 외부 Agent | [customer-template](customer-template/README.md) | 고정 소스·editable·명령·과제·평가 연결 → 작은 baseline |

먼저 [코어 개발환경](../README.md#개발환경-빠른-시작)을 준비하세요.
공통 규칙은 [확장 계약](../docs/adding-components.md), 선택적 모델 예제는
[simple-feedback](simple-feedback/README.md)입니다. 템플릿 stub은 구현 전 명시적으로 실패합니다.
복사 후 등록 파일 경로와 ID를 변경한 다음 `agent-opt plan <실험.toml>` →
`agent-opt doctor --plan <실험.toml> --json`으로 **선언만** 확인합니다. 작은 fixture 실행은
`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v`로
검사하고, 실제 연결은 해당 팀의 Agent/평가기/도구를 준비한 후 작은 `run`의 산출물과
`report.html` 근거로 별도 검증합니다. 검증 종류별 명령은 [CONTRIBUTING](../CONTRIBUTING.md)을 따릅니다.
