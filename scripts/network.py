"""Run a command (or single-stage docker build) with the optional network contract."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.network import configured_build, host_environment


def main():
    args = sys.argv[1:]
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        print("Usage: python3 scripts/network.py -- COMMAND [ARG ...]", file=sys.stderr)
        return 2
    try:
        env = host_environment()
        with configured_build(args, Path.cwd(), env) as command:
            return subprocess.run(command, env=env, shell=False).returncode
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Network command unavailable: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
