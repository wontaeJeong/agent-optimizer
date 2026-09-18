# 개발 지침

## 목적과 경계
- 제품은 범용 Agent Optimizer. ACE-RTL/CVDP/RTL/시뮬레이터 의존성은 examples 안에 둔다.
- 실제 대상 Agent는 별도 repo. 예제는 로컬 소스, 외부 Agent는 고정 commit Git 소스를 사용할 수 있다.
- 같은 기능에 여러 추상 계층을 추가하지 않는다. 현재 Python CLI와 평평한 모듈 구조를 유지한다.
- `docs/architecture.md`, `docs/adding-components.md`, `docs/status.md`를 먼저 읽는다.

## 구현 규칙
- `contracts.py`를 공통 계약으로 사용한다. 알고리즘끼리 직접 호출하지 않는다.
- 후보는 원본을 수정하지 않고 스냅샷에서 생성한다. editable 밖 수정은 거부한다.
- 소스·평가 기준·테스트 수정 권한을 구분한다. 최적화로 점수 계산 자체를 바꾸지 않는다.
- validation으로 후보를 선택하고 test는 선택 이후에만 실행한다. 테스트 점수를 탐색에 사용하지 않는다.
- 미지원/미구현 기능은 명시적으로 실패시킨다. baseline이나 합성 평가로 자동 대체하지 않는다.
- 미수집 지표는 None. partial 사용량을 전체 사용량으로 이름 붙이지 않는다.
- 실행은 argv 배열과 shell=False. 자격증명은 환경/credential store에만 둔다.
- 상용 EDA 도구의 실행 어댑터·설치·라이선스 설정을 추가하지 않는다.
- 개발 로컬 설정 .claude/.codex/.vscode 등은 Git 제외. 공유 AGENTS.md/CLAUDE.md는 커밋 가능.
- 외부 Agent/모델 실행 결과를 검증 없이 성공했다고 문서화하지 않는다.

## 확인 명령
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml
```

핵심 계약·소스/데이터 격리·실행 오류 처리 변경은 관련 테스트를 추가한다.
단순 문서/가역적 저영향 변경에 구현을 그대로 반복하는 테스트를 추가하지 않는다.
