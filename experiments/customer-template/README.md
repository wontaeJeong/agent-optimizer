# 다른 팀 Agent 연결

agent.toml의 source/prompt/editable, harness.toml의 실행 명령을 바꾸고 evaluator.py에 실제 평가를 연결하세요.
experiment.toml의 benchmark는 해당 팀 과제 JSON으로 교체합니다. 템플릿은 일부러 실행 불가능한 경로를
사용합니다. API 없이 실행 가능한 예제는 examples/minimal입니다.
소스가 비공개/수정 불가라면 허용되는 프롬프트·설정만 가진 별도 bundle을 최적화 대상으로 등록하세요.
