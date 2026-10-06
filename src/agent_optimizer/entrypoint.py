"""Installed CLI entry point; preserve doctor/plan read-only imports."""


def main() -> int:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in {"doctor", "plan"}:
        sys.dont_write_bytecode = True
    from agent_optimizer.cli import main as cli_main

    return cli_main()
