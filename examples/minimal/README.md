# 최소 데모

프로젝트 루트에서:
```bash
PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml
```

두 독립 Agent의 소스를 repo 내부 `agents/solo`, `agents/team`에 둡니다.
이들은 실제 LLM/sub-agent가 아니라 합성 텍스트 수정 프로그램입니다.
초기 solo는 수정하지 않으며 file_variants 단계가 repair=true로 바꿉니다.
team은 처음부터 수정합니다. 0→1 결과는 배선 검증 전용이며 세일즈 성능 수치로 쓰지 마세요.
branching.toml은 단계 조건/분기, research-planned.toml은 미구현 알고리즘 명시적 실패 예제입니다.
