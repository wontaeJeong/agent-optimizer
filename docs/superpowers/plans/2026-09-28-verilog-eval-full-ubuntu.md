# Verilog-Eval 두 모드 Ubuntu 전체 평가 구현 계획

> **작업 에이전트:** `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`로 각 Task를 순서대로 실행하고 체크박스를 갱신한다.

**목표:** 고정 Verilog-Eval의 `verilog-spec`와 `verilog-completion` 각각 156개 reference를 Ubuntu x86_64 Icarus v12 공식 평가기에 제출하고, 모든 결과를 비공개 자산 없이 증명한다.

**구조:** 도메인 verifier는 `examples/benchmarks/`에 두어 기존 Dataset provider/VerilogEvaluator를 호출한다. CLI가 선택된 모드의 준비·doctor·전체 enumeration·정답/오답 sanity와 sanitized JSON 저장을 소유한다. 기존 CI의 수동 dispatch에 두 mode matrix를 추가해 각각 독립적으로 실행하고 요약 JSON만 업로드한다.

**기술:** Python 3.12, unittest, Docker Engine, 고정 Icarus v12 이미지, GitHub Actions ubuntu-24.04 x86_64.

**설계:** [승인된 설계](../specs/2026-09-28-verilog-eval-full-ubuntu-design.md).

## 전역 제약

- 전용 `.worktrees/verilog-eval-ubuntu-full`의 `test/verilog-eval-ubuntu-full`에서 진행한다. 기본 checkout main/다른 worktree의 파일이나 브랜치를 수정하지 않는다. 새 작업은 fetch한 `origin/main`에서 시작한다.
- 사용자가 명시 선택한 `verilog-spec`, `verilog-completion`만 허용한다. 각각 고정 Verilog-Eval `c498220d0a52248f8e3fdffe279075215bde2da6`의 156개 과제, 합계 312개를 누락 없이 시도한다. 다른 모드/리비전/이미지로 자동 대체하지 않는다.
- 고정 Icarus v12 commit `4fd5291632232fbe1ba49b2c26bb6b2bf1c6c9cf`의 Docker 이미지 ID·실제 Docker OS/arch를 검사한다. case timeout=90초, 독립 모드 CI job timeout=330분. CI Ubuntu는 `x86_64` / `linux/amd64`여야 한다.
- 신뢰한 verifier만 private `_ref.sv`/`_test.sv`를 만지며 output submission은 TopModule reference 하나다. 공개 artifact는 sanitized summary JSON만이며 private log/source/test/ref 및 키를 업로드하지 않는다.
- 참조 정답 156건 모두 실제 evaluator passed=1이고 해당 모드의 `Prob001_zero` 오답이 **정상 컴파일 후 mismatch/failed=0**이어야 해당 CI job 성공이다. 누락·환경 오류·시험 점수 0/null 중 하나라도 있으면 실패하고 기록한다. 모델 Agent 전체 성능/논문 재현으로 서술하지 않는다.
- API-free 계약 테스트, Mac 실도구 소규모 probe, PR 검사, 사용자 승인 PR 병합, 그 뒤 수동 Ubuntu 전체 workflow와 날짜별 증거의 순서를 분리한다.

## 파일 책임 지도

- `examples/benchmarks/verify_verilog_eval_full.py`: source/data/runtime 준비·검증, reference 변환과 전 task 평가, sanitized 상태 지속 및 CLI/exit.
- `tests/test_verilog_full.py`: fake provider/evaluator의 2모드 전체 enumeration·실패·출력 정보 제한·reference 변환 계약.
- `.github/workflows/ci.yml`: 기존 manual dispatch에 opt-in boolean, Ubuntu x86_64 고정 matrix/timeout, 공개 summary artifact만 업로드.
- `examples/benchmarks/README.md` 또는 기존 안내 문서: 수동 검사 방법·private 경계.
- `docs/SOURCES.md`, `docs/status.md`, `docs/verification.md`: 소비 파일·고정 버전과 실제 Mac/Ubuntu 결과 및 미검증 구분.

---

### Task 1: 전 과제 평가 loop와 sanitized 요약

**Files:**
- Create: `examples/benchmarks/verify_verilog_eval_full.py`
- Create: `tests/test_verilog_full.py`

**Interfaces:**
- Consumes: `Task` 목록, `VerilogEvaluator.evaluate(task, output_dir, timeout_seconds) -> Evaluation`.
- Produces: `reference_submission(directory: Path, problem_id: str) -> str`, `verify_tasks(tasks: list[Task], evaluator, out: Path, mode: str, *, timeout: float = 90) -> dict`.

- [ ] **Step 1: 코어 준비·실패하는 테스트 작성.** `make setup-core`로 `.venv`를 만든다. 임시 pinned 모양의 두 모드 디렉터리에 `Prob001_zero_ref.sv`, `_test.sv`와 다른 task 한 개를 둔다. 정답 텍스트에서 `module RefModule` 선언 **한 번만** `module TopModule`로 바꾸고 동일 파일의 다른 text, test/ref는 수정하지 않는지 검사한다. RefModule 누락/두 번, 디렉터리 밖/symlink는 오류다. 가짜 evaluator가 reference의 status/score를 돌려줄 때 task를 sorted ID로 모두 시도하고 첫 실패 뒤 다음 task도 실행하는지, 한 case exception/timeout/null은 성공 수에 더하지 않고 마지막 summary에 잔여/attempted가 남는지 검사한다. 단 하나의 항목에도 private test/ref 텍스트·raw log 경로가 출력 JSON에 포함되지 않는지 확인한다. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_verilog_full.py -v`를 RED로 확인한다.
- [ ] **Step 2: 최소 구현.** `reference_submission`은 `safe_path(directory, problem_id + "_ref.sv")`에서 읽고 줄 시작의 `re.subn(r"(?m)^([ \t]*)module[ \t]+RefModule\b", r"\1module TopModule", source)`가 정확히 한 건이 아닐 때 `ConfigurationError`다. evaluator `output_dir`은 verifier가 소유하는 `runs/verilog-eval-full/<dataset>/cases/<id>/output`이고 candidate는 `solution.sv` 파일 한 개다. `_test.sv`와 `_ref.sv`는 evaluator만 자체 채점 workspace에 복사한다.

```python
summary = {"dataset": mode, "expected": 156, "attempted": 0,
           "cases": [], "status": "running"}
write_json(out / "summary.json", summary)
for task in sorted(tasks, key=lambda row: row.id):
    result = evaluator.evaluate(task, candidate_dir, timeout)
    summary["cases"].append({"id": task.id, "status": result.status,
                             "passed": result.metrics.get("passed"),
                             "reason": classify(result.status, result.feedback)})
    summary["attempted"] += 1
    write_json(out / "summary.json", summary)
```

  `classify`는 고정 enum(`passed`, `mismatch`, `compile_failure`, `timeout`, `infrastructure_error`, `reference_invalid`)만 반환하고 private feedback 문자열을 summary에 복사하지 않는다. `evaluate`가 예외를 내도 해당 ID에 environment/unsupported 분류를 남기고 나머지 ID 평가를 이어 간다. 준비·계획 오류 전에 summary부터 작성한다. `cases` 공개 ID와 상태의 반복 기록만 사용하고 모드 간 점수 합산은 하지 않는다.
- [ ] **Step 3: GREEN·커밋.** focused 테스트 및 `tests/test_verilog_live.py`의 미준비 skip 범위, `make lint`를 확인한다. `git status`, diff, `git diff --check`, `git log --oneline -10`을 보고 두 파일만 커밋한다. 메시지: `Verilog-Eval 전체 reference 검증기 추가`.

### Task 2: 선택 모드의 고정 준비·오답 sanity·종료 판정

**Files:**
- Modify: `examples/benchmarks/verify_verilog_eval_full.py`
- Modify: `tests/test_verilog_full.py`

**Interfaces:**
- Consumes: Task 1의 `reference_submission`, `verify_tasks`; `Registry.load_project`의 두 Dataset provider, `Provider.prepare`·`doctor`, `load_tasks`, `VerilogEvaluator.validate_benchmark`.
- Produces: `main(argv: list[str] | None = None) -> int`와 `--dataset`/`--require-ubuntu-amd64` 명령.

- [ ] **Step 1: CLI·준비 실패 테스트 RED.** `--dataset` 필수, 선택지는 `verilog-spec|verilog-completion`만, unknown/injected path는 provider 호출 전에 종료 2. 모의 provider.prepare 오류·doctor 실패·task 개수 155·revision/이미지 ID mismatch는 summary의 `expected=156, attempted=0`과 안전한 오류 범주를 기록한 뒤 비영 종료한다. 성공 모드는 156건 모두 시도하고 `Prob001_zero`에 고정 오답 `module TopModule(output zero); assign zero = 1'b1; endmodule`을 추가 평가한다. 오답의 compile failure는 기능 불일치 성공 근거가 아니므로 불합격이다. Mac 실행은 `--require-ubuntu-amd64`가 없을 때만 허용하고, 플래그를 쓰면 `uname -m != x86_64` 또는 Docker `linux/amd64` 불일치에서 모델 없이 종료한다. 실패 테스트를 `test_verilog_full.py`에서 RED로 확인한다.
- [ ] **Step 2: 기존 provider 배선 구현.** argparse의 `--dataset`을 명시하도록 하고 ROOT의 `external/datasets/<dataset>`에서 `Registry().load_project(ROOT).resolve("datasets", args.dataset)()`의 `prepare(cache)`와 `doctor(cache)`를 호출한다. `load_tasks(Path(prepared["benchmark"]))`로 public task metadata를 검사하고 `VerilogEvaluator({**prepared["evaluation_runtime"], **prepared["evaluator_config"]})`로 evaluator를 만든다. prepare 시작 전 summary를 기록하고, public task ID가 156개가 아니거나 revision/이미지 lock/평가기 preflight가 실패하면 attempted=0/환경 사유로 정지한다. 고정 first task `Prob001_zero`가 없으면 억지로 다른 task를 사용하지 않는다. 전체 reference 156/156 passed + 오답 mismatch 증거만 status=passed/exit0이다. 각 비성공 원인은 public enum/Task ID만 summary에 저장한다.

```python
for item in provider.doctor(cache):
    if item["status"] != "ok":
        raise UnavailableError("Pinned Verilog-Eval assets are not ready")
tasks, metadata = load_tasks(Path(prepared["benchmark"]))
if len(tasks) != 156 or metadata["source_revision"] != REVISION:
    raise ConfigurationError("Verilog-Eval pinned task inventory is incomplete")
evaluator = VerilogEvaluator({**prepared["evaluation_runtime"],
                              **prepared["evaluator_config"]})
evaluator.validate_benchmark(tasks, metadata)
```

- [ ] **Step 3: GREEN·커밋.** focused unittest, `test_catalog.py`, `test_verilog_live.py`(환경 미준비 시 skip)와 lint를 실행한다. 수동 CI가 실행될 때만 실제 Git clone/image build가 일어나도록 테스트는 fake provider를 사용한다. diff/log/status 검토 후 두 파일만 커밋한다. 메시지: `선택 Verilog-Eval 모드 준비와 엄격 판정 연결`.

### Task 3: opt-in Ubuntu x86_64 수동 CI

**Files:**
- Modify: `.github/workflows/ci.yml:6-13,137-`
- Modify: `tests/test_verilog_full.py` (workflow 계약 회귀가 필요한 경우)

**Interfaces:**
- Consumes: Task 2의 `--dataset` 및 `--require-ubuntu-amd64`.
- Produces: `workflow_dispatch.inputs.verilog_eval_full`와 `verilog-eval-full` matrix job의 mode별 sanitized summary artifact.

- [ ] **Step 1: 안전한 workflow 구조 테스트 RED.** 새 입력의 default false, 수동 조건만 job 실행, matrix에 두 ID만, `runs-on: ubuntu-24.04`, `timeout-minutes: 330`, 부트스트랩 uv==0.10.7/Python 3.12, 실제 `uname -m`/Docker arch 검사, `.venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset <matrix.dataset> --require-ubuntu-amd64`, artifact path가 오직 summary.json이고 `if: always()`인지 검증한다. 기존 default PR Python3.11/3.12 CI와 수동 ACE official job 설정은 그대로. 테스트를 먼저 RED로 관찰한다.
- [ ] **Step 2: 최소 YAML 배선.** `workflow_dispatch.inputs.verilog_eval_full`은 boolean/default false. 새 job은 아래 골격을 기존 `ci.yml`의 끝에 추가한다. `actions/upload-artifact@v4`는 실패해도 summary만 업로드하고 checkout에서 credentials persist=false로 둔다.

```yaml
  verilog-eval-full:
    name: Verilog-Eval full (${{ matrix.dataset }})
    if: github.event_name == 'workflow_dispatch' && inputs.verilog_eval_full
    runs-on: ubuntu-24.04
    timeout-minutes: 330
    strategy:
      fail-fast: false
      matrix:
        dataset: [verilog-spec, verilog-completion]
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 프로젝트 의존성 준비
        run: make setup-core
      - name: 선택 모드의 전체 평가
        run: .venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset '${{ matrix.dataset }}' --require-ubuntu-amd64
      - name: 정제된 결과만 보존
        if: always() && github.server_url == 'https://github.com'
        uses: actions/upload-artifact@v4
        with:
          name: verilog-eval-full-${{ matrix.dataset }}-${{ github.run_id }}
          path: runs/verilog-eval-full/${{ matrix.dataset }}/summary.json
```

  실제 job `run`에서 `uname -m`·Docker `linux/amd64` 결과를 검증기 내부와 로그에 **비밀 없이** 남긴다. 두 모드의 Docker 준비/시험 로그는 artifact에 넣지 않는다. CI default 테스트 job/smoke와 독립이다.
- [ ] **Step 3: GREEN·커밋.** 관련 test, `make lint`, workflow YAML 문법/Actions 조건식을 검사한다. 기존 CI에서 PR 빌드가 새 full job을 자동 실행하지 않는지 확인하고, 의도 파일만 커밋한다. 메시지: `Verilog-Eval 두 모드 Ubuntu 전체 평가를 수동 CI에 연결`.

### Task 4: Mac 소규모 실도구 검사·사용 안내·PR

**Files:**
- Create: `examples/benchmarks/README.md`
- Modify: `docs/SOURCES.md:65-78`
- Modify: `docs/status.md:61-77`
- Modify: `docs/verification.md` (새 날짜 근거)
- Modify: `tests/test_verilog_full.py` (Mac에서 확인한 실제 범위를 API-free 회귀와 구분하는 경우)

**Interfaces:**
- Consumes: Task 1~3의 준비/검증기·수동 workflow.
- Produces: 명시적 두 모드 명령, Mac ARM64 `Prob001_zero` 정답/오답 실제 평가와 Ubuntu pending 상태, PR 설명.

- [ ] **Step 1: 실제 Mac 범위.** `make doctor-core` 뒤 `.venv/bin/python examples/benchmarks/verify_verilog_eval_full.py --dataset verilog-spec` 및 같은 방식 completion은 **전체 156건을 바로 호출하지 않는다**. 검증기에 `--smoke-one` 플래그를 추가하고 `Prob001_zero` 정답+오답만 평가하며 summary scope=smoke로 분리해 전체 156 성공을 표시하지 않는다. 플래그의 오작동/종료 코드/scope는 focused 테스트 RED→GREEN으로 확보한다. 선택 두 모드의 pinned source/image 준비와 Mac Docker `linux/arm64` 정답/오답을 각각 확인한다. 환경 실패 시 단계별 결과를 기록하고 성공으로 문서화하지 않는다.
- [ ] **Step 2: 안내·검증.** 모드별 명령, private 파일 경계, 초기에 Docker 이미지 빌드가 오래 걸리는 점, 결과 JSON의 status 의미, Ubuntu full은 **병합 뒤 수동 실행 전까지 미검증**임을 예제 README와 status/SOURCES/verification에 적는다. 코어 full unittest 1회, `make lint`, 최소 합성 demo 및 `git diff --check`로 종료 검사. 정보 문서에 실제 task 패스 수를 추정해 쓰지 않는다.
- [ ] **Step 3: 최종 리뷰·PR.** 변경/최근 커밋·origin/main 최신 참조·전체 diff를 검토하고 secrets/private source가 staged/PR artifact에 없는지 확인한다. 브랜치 커밋·push·PR 생성 후 CI Python3.11/3.12·문서 검사를 확인한다. PR 본문에 Mac 증거와 Ubuntu 수동 작업의 미검증을 분리한다. 사용자 승인을 받기 전 merge 또는 auto-merge 예약 금지.

### Task 5: 병합 후 Ubuntu 전체 평가 증거

**Files:**
- Modify: `docs/verification.md` (실제 실행 뒤 결과)
- Modify: `docs/status.md` (실제 실행 뒤 지원 범위)

**Interfaces:**
- Consumes: 병합된 `main`의 수동 `ci.yml` job.
- Produces: 모드별 156개 전체 reference의 실제 상태·workflow/run ID·Ubuntu/이미지 ID·실패 사유 또는 차단 기록.

- [ ] **Step 1: 승인·수동 dispatch.** Task 4 PR을 사용자 승인 뒤 병합한다. `gh workflow run ci.yml --ref main -f verilog_eval_full=true`를 정확히 한 번 실행한다. `gh run list --workflow ci.yml`/`gh run view RUN_ID --json jobs,conclusion,headSha`로 workflow ID를 특정하고 두 matrix job을 확인한다.
- [ ] **Step 2: 실제 판정.** `gh run watch RUN_ID`와 job별 결과를 확인하고 공개 summary artifacts를 `gh run download RUN_ID --name ...`로 내려받아 `expected/attempted/passed/failed`와 `Prob001_zero` 정답·오답 각 status를 검사한다. 플랫폼 `x86_64`/Docker `linux/amd64`, source SHA/image ID와 두 모드 각각 156개 여부를 대조한다. 누락/환경 실패는 실패로 보고하고 다시 실행하려면 원인을 정리한 뒤 새 승인 예산으로 진행한다.
- [ ] **Step 3: 날짜별 근거.** 실제 명령·환경·run ID·모드별 결과만 새 작업 브랜치/워크트리의 docs에 기록한다. 312개 전체 성공은 두 job 모두 실제 성공일 때만 사용한다. 테스트·lint 후 검증 PR을 만들며 병합은 별도 승인 후 진행한다. 실패 시 차단 상태/잔여 과제 수를 정확히 보고한다.

## 완료·인계

코어 코드/평가기의 점수 계산, 상용 EDA 경로, 비공개 source 포함/공개 upload를 변경하지 않는다. 모델/Agent 성능 향상 주장은 하지 않는다. 리뷰 지적은 테스트 선행으로 수정하고, 작업 종료시 기본 디렉터리 `main`과 전용 브랜치·워크트리 상태를 확인한다.
