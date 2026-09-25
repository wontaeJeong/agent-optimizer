"""Installed CLI entry point; preserve doctor read-only imports."""


def main() -> int:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        sys.dont_write_bytecode = True
    from agent_optimizer.cli import main as cli_main

    return cli_main()
