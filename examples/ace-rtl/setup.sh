#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
python3 examples/ace-rtl/environment/setup.py
PYTHONPATH=src python3 examples/ace-rtl/prepare.py external/cvdp_benchmark/example_dataset/cvdp_v1.1.0_example_nonagentic_code_generation_no_commercial.jsonl
