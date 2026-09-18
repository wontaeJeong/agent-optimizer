# Harness extension

command.py: argv wrapper, opencode.py: OpenCode JSON events.
Claude Code, Codex, OpenAgent는 동일한 RunRequest/ExecutionResult 규약으로 추가합니다.
초기에는 command wrapper를 사용하고 필요할 때 전용 trace/usage parser를 구현하세요.
CLI 이름만 바꾸어 완전한 호환성을 주장하지 마세요. 버전, 인증, 종료·에러, child usage를 확인해야 합니다.
