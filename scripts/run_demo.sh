#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
  printf '%s\n' '코어 환경이 없습니다. make setup-core로 준비하세요.' >&2
  exit 2
fi
PYTHONPATH=src "$repo_root/.venv/bin/python" -m agent_optimizer run examples/minimal/experiment.toml
