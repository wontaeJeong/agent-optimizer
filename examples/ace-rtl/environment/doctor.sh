#!/usr/bin/env bash
set -euo pipefail
docker info >/dev/null
docker compose version
docker image inspect nvidia/cvdp-sim:v1.0.0 --format '{{.Id}}'
docker run --rm nvidia/cvdp-sim:v1.0.0 sh -c 'command -v iverilog vvp verilator yosys'
docker image inspect agent-optimizer-opencode:local --format '{{.Id}}'
