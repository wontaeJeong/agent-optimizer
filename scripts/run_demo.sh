#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
PYTHONPATH=src python3 -m agent_optimizer run examples/minimal/experiment.toml
