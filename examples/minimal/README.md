# 최소 데모

`make setup ARGS="--core"`로 준비한 뒤 프로젝트 루트에서:
```bash
PYTHONPATH=src .venv/bin/python -m agent_optimizer run examples/minimal/experiment.toml
```

두 독립 Agent의 소스를 repo 내부 `agents/solo`, `agents/team`에 둡니다.
이들은 실제 LLM/sub-agent가 아니라 합성 텍스트 수정 프로그램입니다.
초기 solo는 수정하지 않으며 file_variants 단계가 repair=true로 바꿉니다.
team은 처음부터 수정합니다. 0→1 결과는 배선 검증 전용이며 세일즈 성능 수치로 쓰지 마세요.
단계 조건/분기 `branching.toml`과 연구 슬롯 `research-planned.toml`은 활성 예제에서 **보류**되었습니다.
과거 파일과 복원 조건은 [deferred 안내](../../deferred/README.md)를 참고하세요.
