# MVP 개발 명령과 문서 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 개발 명령의 범위와 도움말·옵션 전달을 명확히 하며 우발적 셸 실행과 오래된 빌드 경로를 제거한다.

**Architecture:** Makefile은 옵션 문자열을 셸 명령으로 펼치지 않고 bootstrap으로 안전하게 넘긴다. bootstrap은 설치 전에 인수를 검증하며 명령별 도움말을 제공한다. dev.py는 기존 실행 범위를 유지하고 문서는 각 역할에 맞춘다.

**Tech Stack:** GNU/BSD make, POSIX sh, Python 3.11+, unittest, GitHub Actions, Astro/Starlight.

**Spec:** `docs/superpowers/specs/2026-09-27-mvp-first-run-clarity-design.md`.

**실행 중 기준점 갱신:** `origin/main`의 `e470d2f`·`0727b54`가 계획 작성 뒤 합류했다.
Task 1의 안전 파서는 기존 `scripts/make_args.sh`에서, Task 3의 wheel 검증은 기존
`scripts/select_wheel.py`에서 구현한다. 참조처 없는 `scripts/run_demo.sh`는 main의 삭제를
유지하고 `make demo`를 사용한다. 이 메모는 아래 최초 계획과 실제 수정 파일의 차이를 기록한다.

## Global Constraints

- 최신 `origin/main`의 전용 워크트리에서 작업하고 기본 저장소의 main은 유지한다.
- 옵션 없는 `setup`/`doctor`는 ACE 전체, `setup-core`/`doctor-core`는 코어이며 help/doctor는 설치하지 않는다.
- `ARGS`의 정상 `--core`, `--dataset ID`, `--platform "linux/arm64"`, `--json` 조합을 전달한다. 셸/Make 재평가나 `eval`을 사용하지 않는다.
- `doctor --json`의 stdout 단일 JSON, 기존 종료 코드·명령 진입점·모델 호출 조건을 보존한다.
- 예제와 코어 분리, train/validation/test 및 원본·private 평가 격리를 유지한다.

---

### Task 1: Make ARGS를 실행 텍스트로 해석하지 않기

**Files:**
- Modify: `Makefile:1-12`, `scripts/bootstrap.sh:174-278`
- Test: `tests/test_dev_onboarding.py:23-514`, `tests/test_terminal_colors.py`

**Interfaces:**
- Consumes: Make의 명령행 `ARGS`, bootstrap의 기존 `<command> [options]` argv.
- Produces: `make <command> ARGS='...'`의 안전한 옵션 argv와 기존 `sh scripts/bootstrap.sh <command> ...` 동작.

- [ ] **Step 1: 실패 테스트 작성.** 임시 Makefile/가짜 Python을 사용한 `BootstrapTests`에 `ARGS='--core; touch <tmp-path>'`, `ARGS='--json $(touch <tmp-path>)'`, 깨진 인용, `ARGS='--platform "linux/arm64"'`, `ARGS='--dataset verilog-spec --json'`을 추가한다. 앞의 세 입력은 부작용 없이 exit 2, 뒤 두 입력은 기존 순서로 argv 전달을 확인한다. `--json`이 성공/실패 모두 단일 JSON인지 기존 진단 mock으로 확인한다.

```python
result = self.invoke("doctor", 'ARGS=--core; touch injected', make=True)
self.assertEqual(result.returncode, 2)
self.assertFalse((self.outside / "injected").exists())
self.assertEqual(self.trace_text(), "")
```

- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v`에서 기존 Make recipe의 셸 주입 재현을 확인한다.
- [ ] **Step 3: 최소 구현.** Make recipe의 `$(ARGS)` 직접 삽입을 없애고 원문 `$(value ARGS)`를 단일 안전 인용 문자열로 `bootstrap.sh`의 전용 `--make-args` 입력에 전달한다. bootstrap은 **문자별** 공백/짝지은 따옴표를 인수 경계로 처리하고 `$`, 백틱, `;`, `|`, `&`, 괄호, 리다이렉션, 줄바꿈 등 실행 구문은 설치/진단 전 거부한다. `set --`로 기존 validator에 전달하며 `eval`/`sh -c`를 쓰지 않는다. 직접 bootstrap 인수는 이 파서를 거치지 않는다.

```make
# 의도: Make가 ARGS의 중첩 확장을 수행하지 않게 value를 사용하고,
# 셸에는 전체 문자열을 단일 안전 인용 인수로 전달한다.
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	  sh "$$(dirname "$$makefile")/scripts/bootstrap.sh" $@ --make-args '$(subst ','"'"',$(value ARGS))'
```

- [ ] **Step 4: 통과 확인.** `test_dev_onboarding.py`와 `test_terminal_colors.py` 실행, `make doctor ARGS='--core --json'`을 `json.loads` 한 번으로 확인한다. 공백 있는 `make -f <경로>` 호환은 기존 Makefile 루트 계산 패턴을 보존하며 테스트한다.
- [ ] **Step 5: 커밋.** `git add Makefile scripts/bootstrap.sh tests/test_dev_onboarding.py tests/test_terminal_colors.py && git commit -m 'Make 옵션의 셸 실행 해석 차단'`.

### Task 2: 명령별 설치 없는 도움말과 개발 명령 의미

**Files:**
- Modify: `scripts/bootstrap.sh:11-48, 180-278`, `scripts/dev.py:65-101`, `src/agent_optimizer/locale.py`
- Test: `tests/test_dev_onboarding.py`, `tests/test_locale.py`, `tests/test_menu.py`

**Interfaces:**
- Consumes: bootstrap의 `<command> --help`와 dev.py argparse 도움말.
- Produces: 특정 명령의 허용 옵션·충돌·준비 범위·출력 파일·다음 명령 안내; help는 도구 조회 전 반환.

- [ ] **Step 1: 실패 테스트 작성.** Python/도구가 없는 테스트 환경에서 `setup`, `doctor`, `test`, `lint`, `demo`, `smoke`, `live`, `menu` 각각의 shell `--help`를 호출해 자신의 옵션/충돌만 보이는지 확인한다. `--core`/`--dataset`/`--model` 충돌 문구, 무설치·stdout 도움말과 `doctor --core --json`의 단일 JSON을 검사한다.

```python
result = self.invoke("doctor", "--help")
self.assertEqual(result.returncode, 0)
self.assertIn("--model", result.stdout)
self.assertIn("--dataset", result.stdout)
self.assertNotIn("installer:", self.trace_text())
```

- [ ] **Step 2: 실패 확인.** 위 테스트에서 `doctor --help`가 전역 help와 같음을 확인한다.
- [ ] **Step 3: 최소 구현.** bootstrap의 `help_command()`가 명령별 option·충돌 표를 출력하게 하고 `show_help`는 외부 도구 조회 전 분기한다. `dev.py` argparse에 setup의 다운로드·fixture/전체 ACE 부작용, doctor 읽기 전용·model 실제 호출, smoke 공식 평가 도구, live 모델/공식 평가 성공 범위를 적는다. 번역은 `locale.py`의 기존 문구와 일치시킨다.

```sh
case "$command" in
  setup) printf '%s\n' 'setup: --core | --dataset ID | ACE 전체(옵션 없음); --offline; --platform (ACE 전체 전용)' ;;
  doctor) printf '%s\n' 'doctor: --core | --dataset ID | ACE 전체(옵션 없음); --json; --model (ACE 전체 전용, 실제 API)' ;;
esac
```

- [ ] **Step 4: 통과 확인.** 관련 세 테스트 파일과 직접 `make help`, `sh scripts/bootstrap.sh doctor --help` 실행.
- [ ] **Step 5: 커밋.** `git add scripts/bootstrap.sh scripts/dev.py src/agent_optimizer/locale.py tests/test_dev_onboarding.py tests/test_locale.py tests/test_menu.py && git commit -m '개발 명령별 준비 범위와 도움말 정리'`.

### Task 3: 데모 진입점과 CI wheel을 실제 산출물에 맞추기

**Files:**
- Modify: `scripts/run_demo.sh`, `.github/workflows/ci.yml:68-71`, `tests/test_installed_cli.py:59-124`, `CONTRIBUTING.md:20-27`
- Test: `tests/test_dev_onboarding.py` 및 wheel 선택 테스트.

**Interfaces:**
- Consumes: 기존 `scripts/run_demo.sh`, CI `dist/`의 wheel, pyproject `[project].version`.
- Produces: 표준 `.venv`를 쓰는 데모, wheel 경로 또는 `dist/` 디렉터리를 입력받는 독립 설치 검증. 현재 버전 wheel이 정확히 하나인지 확인한다.

- [ ] **Step 1: 실패 테스트 작성.** 임시 `dist/`에 다른 버전 wheel/복수 wheel/현재 버전 wheel 이름만 배치하고 `tests/test_installed_cli.py`의 선택 함수가 누락·복수에서 명확한 오류인지 검사한다. 실제 설치 검증은 정상 wheel에만 수행한다.

```python
def current_wheel(directory: Path) -> Path:
    import tomllib
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    matches = list(directory.glob(f"agent_optimizer-{version}-*.whl"))
    if len(matches) != 1 or len(list(directory.glob("*.whl"))) != 1:
        raise ValueError("현재 프로젝트 wheel 하나가 필요합니다; 빌드 산출물을 확인하세요")
    return matches[0]
```

- [ ] **Step 2: 실패 확인.** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_dev_onboarding.py -v`의 새 선택 함수 case를 실행한다.
- [ ] **Step 3: 최소 구현.** `tests/test_installed_cli.py`에서 wheel 파일 직접 인수는 유지하고 `dist/` 디렉터리도 위 규칙으로 수용한다. CI는 `python tests/test_installed_cli.py dist/`로 변경한다. `scripts/run_demo.sh`는 `.venv/bin/python -m agent_optimizer run ...`를 사용하며 누락 시 `make setup-core`를 알린다. CONTRIBUTING의 wheel 명령도 동일하게 수정한다.

```bash
if [ ! -x "$repo_root/.venv/bin/python" ]; then
  printf '%s\n' '코어 환경이 없습니다: make setup-core' >&2
  exit 2
fi
PYTHONPATH=src "$repo_root/.venv/bin/python" -m agent_optimizer run examples/minimal/experiment.toml
```

- [ ] **Step 4: 통과 확인.** `.venv/bin/python -m build`, `.venv/bin/python tests/test_installed_cli.py dist/`, `sh scripts/run_demo.sh` 실행. 경로와 stdout JSON을 확인한다.
- [ ] **Step 5: 커밋.** `git add scripts/run_demo.sh .github/workflows/ci.yml tests/test_installed_cli.py tests/test_dev_onboarding.py CONTRIBUTING.md && git commit -m '표준 데모 환경과 현재 wheel 검증 경로 정리'`.

### Task 4: 개발·팀·상태 문서 맞추기

**Files:**
- Modify: `AGENTS.md`, `CONTRIBUTING.md`, `docs/development.md`, `docs/status.md`, `docs/FUTURE.md`, `experiments/README.md`, `experiments/dataset-template/README.md`, `website/src/content/docs/developer/validation.md`

**Interfaces:**
- Consumes: Tasks 1–3 실제 도움말과 사용자 계획의 출력 경로.
- Produces: README → 팀 템플릿 → 계약 시작점과 변경 유형별 검증·설치 부작용·보류 기능 설명.

- [ ] **Step 1: 문서와 명령의 충돌 확인.** `make help`, `make setup-core`, `make doctor-core`, `make demo`, `agent-opt plan/doctor --plan`, `make smoke`의 실제 결과·파일을 비교하고 최근 `report_schema_version=3` 구현을 대조한다.
- [ ] **Step 2: 범위별 문서 수정.** AGENTS에는 최신 명령과 안전 경계만, CONTRIBUTING에는 변경 유형별 최소 검사, development에는 Make → bootstrap → dev.py 및 범위별 옵션·실패 복구 표, status/FUTURE에는 v3·현재 TUI 결과 이력/새 설정 선택과 보류 UI를 명시한다. Dataset 템플릿·website 팀 문서는 한국어와 독립 fixture/실연동 완료 의미로 통일한다.

```markdown
`plan`과 `doctor --plan`은 선언·자산의 정적 확인입니다. 실제 Agent·평가기의 실행 여부는
작은 `run`의 `summary.json`, `events.jsonl`과 평가 원본으로 확인합니다.
```

- [ ] **Step 3: 최종 검증.** `make lint`, `make test`, `make demo`, `git diff --check`, `website/`에서 `npm ci && npm run build`. 최신 origin/main의 TUI 4번 결과 이력 테스트도 보존한다. Docker·외부 모델·공식 평가는 미준비 시 실행하지 않았다고 기록한다.
- [ ] **Step 4: 커밋.** `git add AGENTS.md CONTRIBUTING.md docs/development.md docs/status.md docs/FUTURE.md experiments/README.md experiments/dataset-template/README.md website/src/content/docs/developer/validation.md && git commit -m '개발·검증 문서의 실제 준비 범위 정리'`.
