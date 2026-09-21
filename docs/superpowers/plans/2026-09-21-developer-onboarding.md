# Developer Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh checkout diagnosable and ready for development through Makefile commands and a Python-independent bootstrap.

**Architecture:** Keep Makefile as aliases, bootstrap as the minimal shell bridge to Python, and development command orchestration in scripts/dev.py. Put generic diagnostic aggregation in scripts/dev_doctor.py and ACE-specific read-only checks in examples/ace-rtl/environment/diagnostics.py; reuse existing setup verification contracts and pinned inputs.

**Tech Stack:** POSIX sh, Make, Python standard library/unittest, uv, Docker/Compose, existing GitHub Actions.

**Spec:** docs/superpowers/specs/2026-09-21-developer-onboarding-design.md

## Global Constraints

- Mac 및 Ubuntu를 대상으로 기존 Python 개발 도구를 확장하고 Makefile을 공통 진입점으로 둔다. 기본 명령은 전체 예제 환경을 준비한다.
- Git 및 Docker Engine/Compose는 사전 설치 대상으로 진단하고 OS별 설치 안내를 제공한다.
- uv, Python 3.12, 프로젝트 개발 의존성, 고정 외부 소스·데이터, 평가·Agent 이미지는 자동 준비한다.
- 실제 모델 호출은 사용자가 `live`를 실행할 때만 수행한다.
- doctor는 의존성 설치, 소스 수정, 이미지 다운로드, 모델 호출을 하지 않는다.
- 기존 CI의 uv 0.10.7을 새 설치 기준으로 사용하며 사용자 shell 설정을 수정하지 않는다.
- offline은 bootstrap을 포함하여 다운로드·이미지 빌드로 부족한 환경을 보완하지 않는다.
- 일반 출력은 사람이 읽는 요약이며 `--json`은 단일 JSON 문서만 stdout에 쓴다.
- Python subprocess calls use argv arrays and shell=False; credentials never appear in output; upstream SHAs and dependency locks do not change.
- Preserve existing smoke/live identity verification, negative verdicts, source preservation, Python 3.11/3.12 core CI and domain separation.

## File responsibilities and execution order

1. `scripts/dev_doctor.py`, example `environment/diagnostics.py`, doctor routing in `scripts/dev.py`, `tests/test_dev_doctor.py`: read-only diagnosis and structured output.
2. `scripts/bootstrap.sh`, `Makefile`, `scripts/dev.py`, progress in example `environment/setup.py`, `tests/test_dev_onboarding.py`: executable onboarding/development flow.
3. README, CONTRIBUTING, `docs/development.md`, verification/status/SOURCES and existing CI: discoverability, CI entrypoint coverage, actual local environment evidence.

Tasks are sequential because tasks 1/2 share dev.py. Task implementers do not spawn agents. Controller owns per-task and whole-branch review, integration decisions and PR creation.

### Task 1: Read-only aggregate doctor

**Files:** Create `scripts/dev_doctor.py`, `examples/ace-rtl/environment/diagnostics.py`, `tests/test_dev_doctor.py`; modify doctor routing in `scripts/dev.py` and only related old doctor tests in `tests/test_dev_environment.py` when necessary.

**Interfaces:**
- Produces `collect_report(root: Path, platform: str | None = None) -> dict` and `render_report(report: dict, *, json_output: bool = False) -> None` in dev_doctor.
- Report shape: `{"ready": bool, "areas": {"core": bool, "evaluation": bool, "live": bool}, "checks": [{"id": str, "area": str, "status": "ok"|"error"|"blocked", "message": str, "remedy": str}]}`. `ready` requires core and evaluation, not live. `live` readiness requires core/evaluation plus key/model checks.
- Produces example-specific `collect_checks(root: Path, platform: str | None = None) -> list[dict]` in diagnostics.py. The generic collector loads this explicitly as an example adapter, with no ACE implementation logic in src/.
- CLI `main(argv=None)` accepts existing calls without an argument. Doctor uses report rendering and returns 0 if ready, 2 otherwise.

- [ ] Write tests for a fresh checkout collecting independent missing Git/uv/venv/Docker/source/data/lock and live configuration errors; subprocess timeout; corrupted lock (invalid JSON and wrong field types); drift; valid image tags with failed actual tools; JSON secrecy and single-document stdout. Use temporary roots and argv-aware fake subprocess outputs, not production Docker/network.

```python
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    with patch.object(doctor.shutil, "which", return_value=None):
        report = doctor.collect_report(root)
    self.assertFalse(report["ready"])
    self.assertGreater(len([c for c in report["checks"] if c["status"] == "error"]), 1)
    self.assertTrue(all(c["remedy"] for c in report["checks"] if c["status"] != "ok"))
    self.assertEqual(list(root.iterdir()), [])
```

- [ ] Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_dev_doctor -v` and capture RED before implementation.
- [ ] Implement a small diagnostic runner with fixed success/error messages, timeouts, dependency-aware blocked statuses and no raw process output. Check host Git/uv, actual project interpreter/install/dev tools, Docker/Compose/platform, lock schema, source identity/dirty state, asset hashes, driver lock/packages, both image identities/platforms, actual simulator/OpenCode execution and live config. Never call mutating prepare functions from doctor. Do not leak secrets through malformed platform/model/lock values.

```python
def collect_report(root, platform=None):
    checks = core_checks(root) + example_checks(root, platform) + live_checks()
    areas = {area: all(c["status"] == "ok" for c in checks if c["area"] == area)
             for area in ("core", "evaluation", "live")}
    ready = areas["core"] and areas["evaluation"]
    areas["live"] = ready and areas["live"]
    return {"ready": ready, "areas": areas, "checks": checks}
```

- [ ] Route doctor separately from smoke/live early in dev.py so missing lock does not preempt aggregation. Preserve smoke/live behavior. Source-loading for tests must support temporary roots without depending on example code existing inside those roots.
- [ ] Run new tests plus `PYTHONPATH=src:tests .venv/bin/python -m unittest test_dev_environment -v`; fix regressions without weakening identity assertions. Run Ruff on changed Python files.
- [ ] Inspect status/diff/log; commit only this task with `Add actionable read-only development diagnostics`. Write report with exact commands, RED/GREEN evidence and concerns.

### Task 2: Bootstrap, Makefile and developer commands

**Files:** Create `scripts/bootstrap.sh`, `Makefile`, `tests/test_dev_onboarding.py`; modify `scripts/dev.py`, example `environment/setup.py`; update related tests only when interface behavior changes intentionally.

**Interfaces:**
- Consumes `collect_report(root, platform=None)` and `render_report(report, json_output=False)` from Task 1.
- Public commands: setup/doctor/test/lint/demo/smoke/live/help; no arguments means help. `make <command> ARGS="..."` forwards CLI options. setup supports --offline/--platform; doctor supports --json/--platform; smoke/live support --platform. Reject unsupported combinations.
- bootstrap chooses repository `.venv/bin/python` for prepared environments, then compatible system Python for read-only commands, without resolving venv executable symlinks. Setup can install missing uv/Python; all other commands must never bootstrap implicitly. Python-independent shell help is concise and points to full command help.
- Missing uv installation uses official version-specific 0.10.7 installer into repo-local `.cache/uv/bin` (Git ignored), with no shell profile changes; includes that path for all commands. Download installer to a temporary file, check curl/wget exit, then run it; do not pipe unchecked content into shell. Existing uv is reused.

- [ ] Write subprocess-level shell/Make tests with temporary copies and fake PATH executables: help with no Python/uv/Docker; missing prerequisite aggregation; missing uv offline without curl invocation; failed download never executed; newly installed uv accessible; Python absent setup; spaces in root; foreign cwd; no command injection; environment preservation. Mock external tools, not Make or shell itself.
- [ ] Add Python tests for setup progress and order, failure halting, final doctor/demo gating, dev command exit propagation, unsupported arguments and live auth-first behavior. Verify offline reaches uv with offline flags and does not build images.

```python
result = subprocess.run(["sh", str(root / "scripts/bootstrap.sh"), "help"],
                        cwd=outside, env=environment_without_python, capture_output=True, text=True)
self.assertEqual(result.returncode, 0)
self.assertIn("doctor", result.stdout)
self.assertFalse((root / ".venv").exists())
```

- [ ] Run `PYTHONPATH=src:tests .venv/bin/python -m unittest test_dev_onboarding -v` for RED.
- [ ] Implement Makefile default/phony aliases delegating to quoted repository-relative bootstrap. Keep stdout JSON clean (use quiet recipes). Implement bootstrap OS/prerequisite checks, user-local pinned uv installation and Python preparation. Do not install OS packages or start daemons. Route direct Python setup through bootstrap if uv/Python readiness requires it, with explicit recursion avoidance.

```makefile
.DEFAULT_GOAL := help
.PHONY: help setup doctor test lint demo smoke live
help setup doctor test lint demo smoke live:
	@sh "$(dir $(abspath $(lastword $(MAKEFILE_LIST))))scripts/bootstrap.sh" $@ $(ARGS)
```

- [ ] Implement setup stages with flushed progress/log paths, repository-specific UV_PROJECT_ENVIRONMENT, frozen dev sync, existing prepare_environment/dataset preparation, read-only final doctor and minimal demo. Preserve existing wrong driver environment; do not reset sources. Use actual project venv for test/lint/demo, return actionable setup message if unavailable. Failure messages name stage and repair/log path; KeyboardInterrupt returns nonzero without falsely reporting ready.
- [ ] Add progress to existing lengthy preparation operations without bypassing image/source/driver checks. Do not hide failed commands behind success messages. setup --offline must not invoke an installer, Python download or Docker build.
- [ ] Run task tests, Task 1 tests and existing environment tests, plus shell syntax `sh -n scripts/bootstrap.sh`, Make help from root and foreign cwd, Ruff and diff check. Commit as `Add one-command development setup and Make targets`; report exact tests and concerns.

### Task 3: Onboarding documentation, CI and real verification

**Files:** Modify `README.md`, `CONTRIBUTING.md`, `docs/verification.md`, `docs/status.md`, `docs/SOURCES.md`, `.github/workflows/ci.yml`; create `docs/development.md`.

**Interfaces:** Consume final public commands from Task 2. Existing CI core matrix must retain Python 3.11/3.12, real simulator tests, packaging and independent wheel smoke; manual official job remains opt-in and model-free.

- [ ] Add README quick-start with `make setup` and make-less `sh scripts/bootstrap.sh setup`, links to Mac/Ubuntu prerequisite installation, `make doctor`, command table, time/log expectations, first demo/result path and live-only credential requirements. Add troubleshooting matching actual diagnostic IDs/remedies, venv activation and offline reuse. Read actual command help before writing exact examples.
- [ ] Update CONTRIBUTING daily commands and stale verification references; document shell fallback for make, Python/uv bootstrap and how to run full smoke. Add sourced uv/Docker installation reference URLs to SOURCES without updating pinned SHAs.
- [ ] Exercise public make commands in existing CI. Replace core lint/test/demo commands with Make targets while retaining matrix environment; add help. Manual integration uses make setup/doctor/offline/smoke. Ensure uv is on PATH where doctor needs it. No extra workflow or automatic model call.

```yaml
      - name: Developer command help
        run: make help
      - name: Lint
        run: make lint
      - name: Unit and contract tests
        run: make test
      - name: Minimal demo
        run: make demo
```

- [ ] Run `make help`, `make lint`, `make test`, `make demo`, build and `git diff --check`. Run `actionlint .github/workflows/ci.yml` if installed; report if absent. No invented verification evidence.
- [ ] Inspect actual local Docker/Compose availability; run clean-state doctor (expected nonzero with actionable items), `make setup`, `make doctor`, JSON doctor, `make setup ARGS="--offline"`, `make smoke` if prerequisites are available. Use current worktree's isolated external/ assets; don't borrow another worktree's writable environments. Long setup may use existing daemon Docker layer cache. Do not call live. Record platform, counts, artifacts, skips and failure reasons in verification/status; fix discovered correctness bugs with RED/GREEN tests within relevant files before final evidence.
- [ ] Commit docs/CI and actual evidence as `Document and verify the developer onboarding workflow`; report exact results and remaining limitations.

## Controller completion

- Review each task against spec and code quality using an independent agent; fix important findings before the next task.
- Run final whole-branch review and any necessary targeted checks after fixes.
- Inspect all branch commits, diff, status, remote tracking; push only chore/dev-environment and create or update its PR against main.
- Observe core CI and, where available, trigger the existing official manual workflow for native Ubuntu evidence. Record actual outcomes without calling pending checks passed.
- Report PR URL, actual verification and remaining limitations. Ask for merge approval; do not merge automatically.
