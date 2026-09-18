# 작은 RTL Agent

OpenCode로 공개 RTL을 수정하고, 분리된 evaluator에서 Icarus로 검사합니다.
평가 도구는 CVDP 공식 OSS 이미지 안의 Icarus를 재사용하며 별도 simulator Dockerfile을 만들지 않습니다.

```bash
bash examples/ace-rtl/setup.sh
# 사용하려는 OpenCode 버전을 명시적으로 선택해 기록합니다.
export OPENCODE_VERSION=<설치할-정확한-버전>
docker build --build-arg OPENCODE_VERSION="$OPENCODE_VERSION" -t agent-optimizer-opencode:local -f examples/rtl-debugger/Dockerfile .
export AGENT_OPT_MODEL=provider/model
# 해당 provider 인증도 환경변수로 설정. harness.toml env_passthrough를 함께 확인.
uv run agent-opt run examples/rtl-debugger/experiment.toml
```

OpenCode 프로필은 기본 CLI 에이전트를 사용합니다. 예제 Agent overlay 설정을 수정할 수 있습니다.
실제 통합은 이 ZIP 제작 환경에서 실행하지 않았습니다.
