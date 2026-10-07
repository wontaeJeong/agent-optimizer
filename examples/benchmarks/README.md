# Verilog-Eval 고정 reference 검증

명시적으로 고른 `verilog-spec` 또는 `verilog-completion`만 준비합니다. Docker daemon과
`make doctor-core`를 먼저 확인하세요. 첫 실행의 고정 Git checkout과 별도 Icarus v12
이미지 빌드는 오래 걸릴 수 있습니다. 다른 simulator/버전으로 자동 대체하지 않습니다.

Mac 등의 소규모 **실도구** 확인(각 모드 `Prob001_zero` reference 1건 + 고정 오답 1건):

```bash
make doctor-core
PYTHONPATH=src .venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset verilog-spec --smoke-one
PYTHONPATH=src .venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset verilog-completion --smoke-one
```

`runs/verilog-eval-smoke/<dataset>/summary.json`의 `scope=smoke`, `expected=1`,
`attempted=1`은 해당 **한 문제만** 검사했다는 뜻입니다. `actual_task_count=156`은
준비된 목록 크기이지 나머지 155건을 평가했다는 뜻이 아닙니다. `cases[0]`의
`passed=1.0`과 `wrong.reason=mismatch`, `wrong.passed=0.0`을 모두 확인하세요.
`status=passed`는 **해당 scope**에서 정답 통과·오답 mismatch가 확인된 경우에만
설정됩니다. 준비/채점 실패는 `status=failed`/exit 1이고, 잘못된 CLI 조합은
exit 2입니다. summary가 이미 있으면 덮어쓰지 않으므로 별도 작업공간에서 실행하세요.

Ubuntu x86_64 전체 검사는 병합 후 수동 workflow의 두 독립 모드에서만 실행합니다.
동등한 로컬 명령은 다음과 같으며 **`--smoke-one` 없이** 모드별 156개 reference와
고정 오답을 검사합니다. `--smoke-one`과 `--require-ubuntu-amd64`의 조합은 거부됩니다.

```bash
PYTHONPATH=src .venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset verilog-spec --require-ubuntu-amd64 --jobs 2
PYTHONPATH=src .venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset verilog-completion --require-ubuntu-amd64 --jobs 2
```

`--jobs`는 1..16이며 기본 1(직렬), 수동 CI 기본 2입니다. 과제별 output·scoring 경로와
평가 deadline을 분리하고 coordinator 하나가 완료된 판정을 기록합니다. 직렬 비교 CI는
`verilog_jobs=1`을 지정합니다. 누락·실패를 생략하거나 통과로 바꾸지 않습니다.

전체 요약 경로는 `runs/verilog-eval-full/<dataset>/summary.json`입니다. private
`external/datasets/`의 `_test.sv`/`_ref.sv`, `runs/`의 제출물·평가 로그/출력,
키·원본 로그는 공개/업로드하지 마세요. 수동 CI artifact는 정제된 해당 모드
`summary.json`만 사용합니다. 현재 [실행 근거](../../docs/verification.md#2026-09-28-verilog-eval-mac-두-모드-실도구-smoke)는
Mac ARM64의 각 1건이며 **Ubuntu 전체 312건은 병합 후 수동 CI 전까지 미검증**입니다.
