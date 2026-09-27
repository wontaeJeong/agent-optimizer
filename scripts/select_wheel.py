"""Select exactly one freshly built wheel for the isolated CLI check."""

import sys
from pathlib import Path


def main(argv):
    if len(argv) != 1:
        print("사용법: python scripts/select_wheel.py dist", file=sys.stderr)
        return 2
    wheels = sorted(Path(argv[0]).glob("*.whl"))
    if len(wheels) != 1 or not wheels[0].is_file() or not wheels[0].name.startswith("agent_optimizer-"):
        print(f"wheel 파일이 정확히 하나여야 합니다: {argv[0]} (발견: {len(wheels)})", file=sys.stderr)
        return 2
    print(wheels[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
