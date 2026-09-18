# 팀 개발

| 담당 | 주 작업 위치 | 완료 조건 |
|---|---|---|
| 공통 실행/계약 | src/agent_optimizer/ | 최소 데모와 계약 테스트 통과 |
| 알고리즘별 담당 | optimizers/gepa.py, meta_harness.py, ecdysis.py | propose/evaluate/usage 규약 연결, 상태표 갱신 |
| Agent/Harness | harnesses/, examples/ | 원본 보존, 실행 명령·오류·사용량 범위 문서화 |
| RTL 데모/환경 | examples/ace-rtl/, rtl-debugger/ | 공식 OSS 평가로 한 문제 검증 |

모듈 소유자는 해당 파일과 필요한 테스트를 함께 수정합니다. 공유 계약 변경은 먼저 팀 내 합의하고
예제를 같이 갱신합니다. 실제 담당자 이름이나 CODEOWNERS는 팀에서 정하세요.

`uv sync --frozen`으로 시작하고 `uv run python -m unittest discover -s tests -v`로 확인합니다.
의존성을 추가하면 pyproject.toml과 `uv lock`을 함께 커밋합니다. 알고리즘 라이브러리는 가능하면
optional dependencies로 분리해 최소 데모가 무거운 연구 의존성을 요구하지 않도록 합니다.

PR에는 문제/변경/검증/미검증 영역을 짧게 적습니다. 외부 API 실행은 모델·데이터·예산을 기록합니다.
실험 로그, 외부 소스, 데이터셋, API 키, 개인 IDE/Agent 설정은 커밋하지 않습니다.
이 배포본은 조직의 공개 배포 라이선스를 임의로 선택하지 않았습니다. 외부 공개 시 팀에서 결정하세요.
