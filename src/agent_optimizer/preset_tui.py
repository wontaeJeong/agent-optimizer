"""프리셋 선택의 읽기 전용 설명 및 run-owned ACE 설정 생성."""
from __future__ import annotations

import importlib.util
import math
import os
import shutil
import sys
import uuid
from pathlib import Path

from agent_optimizer.catalog import DATASETS
from agent_optimizer.config import identifier, load_agent, load_experiment, load_tasks, read_toml
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.locale import current_language
from agent_optimizer.registry import PROJECT_COMPONENTS, Registry, is_source_checkout
from agent_optimizer.setup_wizard import _literal, _section, prepare_selection, write_experiment
from agent_optimizer.workspace import safe_path


ACE_GUIDANCE = "skills/ace-rtl/references/role-guidance.md"
ACE_SCAFFOLD = "skills/ace-rtl/scripts/agent_opt_scaffold.py"
SCAFFOLD_CALL = ("import runpy,sys; from pathlib import Path; "
                 "runpy.run_path(sys.argv[1])['prepare_task'](Path(sys.argv[2]))")


def _tr(korean: str, english: str) -> str:
    return english if current_language() == "en" else korean


def preset_options(root: Path, page: str, agent: str = "ace-rtl") -> list[tuple]:
    """프리셋의 호환성·준비 조건을 UI와 분리해 한 곳에서 제공한다."""
    agents = [("ACE-RTL", _tr("고정 Git 소스의 ACE 스킬 프로필 · 준비 후 OpenCode 실행",
                               "Pinned Git ACE skill profile · OpenCode after preparation"), True,
               _tr("자산 준비 필요", "Assets to prepare"))]
    for path in sorted((root / "examples").glob("*/agent.toml")):
        registered_agent = load_agent(path)
        agents.append((registered_agent.id, _tr("등록된 Agent입니다. 전용 설정을 기존 실험 경로에서 선택하세요",
                                      "Registered Agent; select its dedicated experiment in existing runs"), False,
                       _tr("이번 조합과 호환 불가", "Not compatible")))
    for path in (root / "examples/minimal/solo.toml", root / "examples/minimal/team.toml"):
        if path.is_file():
            registered_agent = load_agent(path)
            agents.append((registered_agent.id, _tr("합성 fixture Agent · sample_text 데이터셋과 조합",
                                          "Synthetic fixture Agent · compatible with sample_text"), True,
                           _tr("구현됨", "Implemented")))
    agents += [(_tr("내 Agent 연결하기", "Connect my Agent"),
                _tr("로컬/Git Agent와 editable을 입력하는 고급 설정", "Advanced local/Git Agent and editable configuration"), True,
                _tr("입력/설정 필요", "Configuration needed")),
               (_tr("기존 Agent 설정 선택", "Select existing Agent configuration"),
                _tr("기존 experiment.toml의 Agent·Harness·Optimizer·Dataset을 확인", "Use an existing experiment.toml configuration"), True,
                _tr("입력/설정 필요", "Configuration needed"))]
    registry = Registry()
    optimizer_options = []
    for name, description in (("gepa", _tr("role-guidance.md 텍스트 수정 · Optimizer 모델 필요", "Edit role-guidance.md · optimizer model required")),
                              ("meta_harness", _tr(f"후보별 {ACE_SCAFFOLD} 실행 · Optimizer 모델 필요", f"Execute candidate {ACE_SCAFFOLD} · optimizer model required")),
                              ("baseline", _tr("변경 없는 기준 측정 · Optimizer 모델 호출 없음", "Unchanged baseline · no optimizer model call"))):
        if name in registry.factories["optimizers"]:
            optimizer_options.append(({"gepa": "GEPA", "meta_harness": "Meta-Harness",
                                       "baseline": "Baseline"}[name], description, True,
                                      _tr("구현됨", "Implemented") if name == "baseline"
                                      else _tr("입력/설정 필요", "Configuration needed")))
    for name in sorted(registry.factories["optimizers"]):
        if name not in {"gepa", "meta_harness", "baseline"}:
            optimizer_options.append((name, _tr("이번 ACE 프리셋의 수정 대상·실행 연결은 확인되지 않음; 고급 설정 사용", "No verified edit surface for this ACE preset; use advanced setup"), False,
                                       _tr("이번 조합과 호환 불가", "Not compatible")))
    if is_source_checkout(root):
        for name in sorted(PROJECT_COMPONENTS["optimizers"]):
            optimizer_options.append((name, _tr("프로젝트 등록 팀 Optimizer · 이번 프리셋의 옵션/수정 파일은 고급 설정에서 지정",
                                                "Project-registered team optimizer; configure its options/editable file in advanced setup"), False,
                                      _tr("입력/설정 필요", "Configuration needed")))
    dataset_options = [("CVDP", _tr("고정 공개 train 1·validation 1 · 공식 evaluator=cvdp · 자산 준비 필요",
                                      "Pinned public train 1 / validation 1 · official evaluator=cvdp · preparation needed"), True,
                        _tr("자산 준비 필요", "Assets to prepare"))]
    dataset_options.extend((name, _tr("ACE OpenCode 과제/평가기 호환성 미확인 · 기존 실험 사용",
                                      "ACE OpenCode task/evaluator compatibility not established; use existing experiment"), False,
                            _tr("이번 조합과 호환 불가", "Not compatible"))
                           for name in sorted(DATASETS) if name != "cvdp")
    if is_source_checkout(root):
        dataset_options.extend((name, _tr("프로젝트 등록 데이터셋 · ACE 출력/평가기 호환성 미확인",
                                          "Project-registered dataset; ACE output/evaluator compatibility not verified"), False,
                                _tr("이번 조합과 호환 불가", "Not compatible"))
                               for name in sorted(PROJECT_COMPONENTS["datasets"]) if name not in DATASETS)
    ace_harness = [("OpenCode", _tr("ACE 프로필 ace-opencode · adapter ace_opencode · Docker/모델 필요",
                                     "ACE profile ace-opencode · adapter ace_opencode · Docker/model required"), True,
                    _tr("자산 준비 필요", "Assets to prepare")),
                   ("Claude Code", _tr("ACE 프로필 구현됨 · 선택형 조합은 기존 실험에서 지정",
                                       "ACE profile implemented · select it via existing experiment"), False,
                    _tr("이번 조합과 호환 불가", "Not compatible"))]
    fixture_harness = [("Fixture", _tr("합성 과제 전용 · 모델·Docker 필요 없음",
                                           "Synthetic tasks only · no model/Docker required"), True,
                        _tr("구현됨", "Implemented")),
                       ("OpenCode", _tr("합성 과제용 OpenCode 프리셋 미검증 · 기존 실험 사용",
                                           "No verified OpenCode fixture preset; use existing experiment"), False,
                         _tr("이번 조합과 호환 불가", "Not compatible"))]
    if is_source_checkout(root):
        for name in sorted(PROJECT_COMPONENTS["harnesses"]):
            row = (name, _tr("프로젝트 등록 팀 Harness · 전용 프로필/argv가 필요하면 고급 설정 사용",
                             "Project-registered team Harness; configure its profile/argv in advanced setup"), False,
                   _tr("입력/설정 필요", "Configuration needed"))
            ace_harness.append(row)
            fixture_harness.append(row)
    own_harness = (_tr("내 Harness 연결하기", "Connect my Harness"),
                   _tr("argv 또는 등록된 파일 플러그인은 고급 설정 사용",
                       "Use advanced setup for argv or registered file plugins"), True,
                   _tr("입력/설정 필요", "Configuration needed"))
    own_optimizer = (_tr("내 Optimizer 연결하기", "Connect my Optimizer"),
                     _tr("등록된 ID 또는 신뢰한 file.py:Symbol · 고급 설정에서 stage 옵션 검증",
                         "Registered ID or trusted file.py:Symbol · validate stage options in advanced setup"), True,
                     _tr("입력/설정 필요", "Configuration needed"))
    own_dataset = (_tr("내 tasks.json 연결하기", "Connect my tasks.json"),
                   _tr("로컬 공개 과제와 명시적 evaluator가 필요 · 채점기를 추측하지 않음",
                       "Local public tasks and explicit evaluator required; no inferred scoring"), True,
                   _tr("입력/설정 필요", "Configuration needed"))
    existing_config = (_tr("기존 experiment.toml 선택", "Select existing experiment.toml"),
                       _tr("기존 파일의 네 선택과 호환성을 계획 검사로 확인",
                           "Validate all four selections in an existing file via plan checks"), True,
                       _tr("입력/설정 필요", "Configuration needed"))
    fixture_optimizers = [("Baseline", _tr("변경 없는 합성 기준 측정", "Unchanged synthetic baseline"), True,
                           _tr("구현됨", "Implemented")),
                          ("FileVariants", _tr("명시적 strategy.json 후보 · 모델 호출 없음",
                                               "Explicit strategy.json candidate · no model call"), True,
                           _tr("구현됨", "Implemented"))]
    fixture_optimizers.extend((name, _tr("이 합성 fixture의 수정/실행 계약 미연결 · 고급 설정 사용",
                                               "No verified edit/execution contract for this fixture; use advanced setup"), False,
                               _tr("이번 조합과 호환 불가", "Not compatible"))
                              for name in sorted(registry.factories["optimizers"])
                              if name not in {"baseline", "file_variants"})
    if is_source_checkout(root):
        fixture_optimizers.extend((name, _tr("프로젝트 등록 팀 Optimizer · 고급 설정에서 옵션/평가기 확인",
                                                "Project-registered team optimizer; check options/evaluator in advanced setup"), False,
                                   _tr("입력/설정 필요", "Configuration needed"))
                                  for name in sorted(PROJECT_COMPONENTS["optimizers"]))
    optimizer_options.extend([own_optimizer, existing_config])
    fixture_optimizers.extend([own_optimizer, existing_config])
    dataset_options.extend([own_dataset, existing_config])
    fixture = agent in {"rtl-solo", "rtl-team"}
    pages = {"Agent": agents,
             "Harness": [*(fixture_harness if fixture else ace_harness), own_harness, existing_config],
             "Optimizer": fixture_optimizers if fixture else optimizer_options,
             "Dataset": [("sample_text", _tr("내장 공개 합성 과제 · evaluator=sample_eval · 실제 RTL/LLM 점수 아님",
                                                "Built-in synthetic tasks · evaluator=sample_eval · not RTL/LLM performance"), True,
                          _tr("구현됨", "Implemented")),
                          ("CVDP", _tr("fixture 출력은 공식 CVDP 채점 형식과 호환되지 않음",
                                            "Fixture outputs are incompatible with official CVDP scoring"), False,
                           _tr("이번 조합과 호환 불가", "Not compatible")), own_dataset, existing_config]
              if fixture else dataset_options}
    return pages[page]


def write_sample_selection(root: Path, agent_id: str, optimizer: str, *, name: str | None = None,
                            max_trials: int | None = None, wall_time: float | None = None,
                            trial_timeout: float | None = None, progress_stream=None) -> Path:
    """등록된 합성 fixture와 evaluator를 기존 init 계약으로만 연결한다."""
    if agent_id not in {"rtl-solo", "rtl-team"} or optimizer not in {"baseline", "file_variants"}:
        raise ConfigurationError("지원하지 않는 합성 프리셋 조합입니다")
    root = root.resolve()
    agent = root / "examples/minimal/agents" / agent_id.removeprefix("rtl-")
    if not (agent / "prompts/system.md").is_file():
        raise ConfigurationError("합성 Agent 파일이 없습니다")
    dataset, plugins, dependencies = prepare_selection(root, "sample_text",
                                                       progress_stream=progress_stream)
    stages = []
    if optimizer == "file_variants":
        stages = [{"id": "file-variants", "optimizer": "file_variants", "max_trials": 1,
                   "config": {"variants": [{"name": "repair", "files": {
                       "configs/strategy.json": '{"repair": true}\n'}}]}}]
    return write_experiment(root / "runs/configs" / (identifier(name) if name else
                                                   "fixture-" + uuid.uuid4().hex[:12]),
                            agent=agent, harness={"adapter": "fixture", "id": "fixture"},
                            dataset=dataset, stages=stages, plugins=plugins, dependencies=dependencies,
                             name=name or f"{agent_id}-{optimizer.replace('_', '-')}-sample-text",
                            agent_id=agent_id,
                            editable=["configs/strategy.json"], project_root=root,
                             max_tasks=3,
                             max_trials=max_trials if max_trials is not None else 3 + len(stages),
                             wall_time=wall_time if wall_time is not None else 3600,
                             trial_timeout=trial_timeout if trial_timeout is not None else 120)


def ace_stage_config(optimizer: str, options: dict | None = None) -> dict:
    """TUI defaults and explicit CLI options use one validated active edit surface."""
    if options is None:
        options = {}
    if optimizer not in {"gepa", "meta_harness", "baseline"}:
        raise ConfigurationError(f"지원하지 않는 ACE Optimizer: {optimizer}")
    if optimizer == "baseline":
        if options:
            raise ConfigurationError("baseline에는 Optimizer 설정을 지정할 수 없습니다")
        return {}
    defaults = ({"file": ACE_GUIDANCE, "metric": "passed", "direction": "maximize",
                 "iterations": 3, "batch_size": 4, "merge": False} if optimizer == "gepa" else
                {"file": ACE_SCAFFOLD, "metric": "passed", "direction": "maximize",
                 "iterations": 3, "required_symbol": "prepare_task"})
    allowed = set(defaults) | {"request_timeout_seconds"} | ({"seed"} if optimizer == "gepa" else set())
    if not isinstance(options, dict) or set(options) - allowed:
        raise ConfigurationError(f"{optimizer}에 지원하지 않는 설정 키가 있습니다")
    config = {**defaults, **options}
    if (config["file"] != defaults["file"] or config["metric"] != "passed"
            or config["direction"] != "maximize"
            or optimizer == "gepa" and config["merge"] is not False
            or optimizer == "meta_harness" and config["required_symbol"] != "prepare_task"):
        raise ConfigurationError("ACE 활성 수정 파일·지표·symbol만 선택할 수 있습니다 (GEPA merge 미지원)")
    for key in ("iterations", "batch_size", "seed"):
        if key in config and (type(config[key]) is not int or
                              (config[key] < 0 if key == "seed" else not 1 <= config[key] <= 100)):
            raise ConfigurationError(f"{optimizer}.{key} 값이 허용 범위를 벗어났습니다")
    if "request_timeout_seconds" in config:
        value = config["request_timeout_seconds"]
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise ConfigurationError("request_timeout_seconds는 양수여야 합니다")
    return config


def write_ace_selection(root: Path, optimizer: str, *, name: str | None = None,
                        options: dict | None = None, max_trials: int | None = None,
                        wall_time: float | None = None, trial_timeout: float | None = None) -> Path:
    """고정 ACE 프리셋을 보존한 채 준비된 공개 두 과제의 독립 실험을 생성한다."""
    stage_config = ace_stage_config(optimizer, options)
    root = root.resolve()
    original = root / "examples/ace-rtl/experiment.toml"
    template = read_toml(original)
    benchmark = root / template["benchmark"]
    if not benchmark.is_file():
        raise ConfigurationError("ACE 공개 tasks.json 준비가 필요합니다")
    tasks, _ = load_tasks(benchmark)
    train = sum(task.split == "train" for task in tasks)
    validation = sum(task.split == "validation" for task in tasks)
    if train != 1 or validation != 1 or any(task.split == "test" for task in tasks):
        raise ConfigurationError("ACE 선택형 데모는 train 1·validation 1과 final_test=false를 사용합니다")
    iterations = stage_config.get("iterations", 3)
    allowance = (train + validation + iterations *
                 (min(train, stage_config.get("batch_size", train)) + validation))
    minimum = validation + (0 if optimizer == "baseline" else allowance)
    maximum = max_trials if max_trials is not None else minimum
    if type(maximum) is not int or maximum < minimum:
        raise ConfigurationError(f"max_trials는 최소 {minimum}이어야 합니다")
    timeout = trial_timeout if trial_timeout is not None else template["budget"]["trial_timeout_seconds"]
    wall = wall_time if wall_time is not None else maximum * timeout + iterations * 60 + 180
    if (type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0 or
            type(wall) not in {int, float} or not math.isfinite(wall) or wall <= 0):
        raise ConfigurationError("ACE 실행 시간 예산은 유한한 양수여야 합니다")
    folder = root / "runs" / "configs" / (identifier(name) if name else "ace-" + uuid.uuid4().hex[:12])
    if (root / "runs").is_symlink() or (root / "runs/configs").is_symlink():
        raise ConfigurationError("실험 설정 디렉터리는 symlink일 수 없습니다")
    if folder.exists() or folder.is_symlink():
        raise ConfigurationError(f"Generated configuration already exists: {folder}")
    folder.mkdir(parents=True, exist_ok=False)
    try:
        prefix = folder.relative_to(root).as_posix()
        source = read_toml(root / template["agents"][0])
        agent_path = template["agents"][0]
        seeds = {}
        if optimizer == "meta_harness":
            script = Path(__file__).with_name("ace_scaffold.py")
            shutil.copyfile(script, folder / "ace_scaffold.py")
            agent_path = prefix + "/agent.toml"
            editable = [*source["editable"], ACE_SCAFFOLD]
            build = ["python3", "-c", SCAFFOLD_CALL, f"agent/{ACE_SCAFFOLD}", "task"]
            agent_lines = ["schema_version = 2", f"id = {_literal(source['id'])}",
                           f"description = {_literal(source['description'])}",
                           f"supported_harnesses = {_literal(source['supported_harnesses'])}",
                           f"prompt_file = {_literal(source['prompt_file'])}",
                           f"editable = {_literal(editable)}", f"build = {_literal(build)}", ""]
            agent_lines += _section("source", source["source"])
            (folder / "agent.toml").write_text("\n".join(agent_lines), encoding="utf-8")
            seeds[ACE_SCAFFOLD] = prefix + "/ace_scaffold.py"
        experiment_name = name or "ace-rtl-opencode-" + optimizer.replace("_", "-")
        lines = ["schema_version = 1", f"name = {_literal(experiment_name)}",
                 f"project_root = {_literal(os.path.relpath(root, folder))}",
                 f"agents = {_literal([agent_path])}",
                 f"harnesses = {_literal(template['harnesses'])}",
                 f"benchmark = {_literal(template['benchmark'])}",
                 'evaluator = "cvdp"', "final_test = false",
                 f"final_stages = {_literal(['baseline'] if optimizer == 'baseline' else [optimizer])}",
                 'output_dir = "runs"', ""]
        if seeds:
            lines += _section("candidate_seed_files", seeds)
        lines += _section("preset_selection", {"agent": "ace-rtl", "harness": "ace-opencode",
                                               "optimizer": optimizer, "dataset": "cvdp"})
        lines += _section("plugins.harnesses", template["plugins"]["harnesses"])
        lines += _section("budget", {"max_trials": maximum, "max_wall_time_seconds": wall,
                                      "trial_timeout_seconds": timeout})
        lines += _section("evaluator_config", {"repo": str(root / "external/cvdp_benchmark"),
                                                "python": str(root / "external/cvdp-venv/bin/python")})
        lines += ["[objective]", 'mode = "lexicographic"', "keep = 1", "",
                  "[[objective.metrics]]", 'name = "solve_rate"', 'source = "passed"',
                  'direction = "maximize"', 'aggregate = "mean"', ""]
        if optimizer != "baseline":
            lines += ["[[stages]]", f"id = {_literal(optimizer)}",
                      f"optimizer = {_literal(optimizer)}", 'inputs = ["baseline"]',
                      f"max_trials = {allowance}", ""]
            lines += _section("stages.config", stage_config)
        target = folder / "experiment.toml"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        load_experiment(target)
        return target
    except Exception:
        shutil.rmtree(folder)
        raise


def verify_ace_selection(spec: dict) -> None:
    """선택형 표지를 붙인 설정이 고정 예제·선택 알고리즘 계약과 같은지 확인한다."""
    root = spec["_root"]
    choice = spec.get("preset_selection")
    try:
        optimizer = choice["optimizer"]
        source = load_agent(root / "examples/ace-rtl/source.toml")
        profile = read_toml(root / "examples/ace-rtl/harness.toml")
        template = read_toml(root / "examples/ace-rtl/experiment.toml")
        agent = spec["_agents"][0]
        optimizer_config = spec["stages"][0]["config"] if optimizer != "baseline" else {}
        expected_config = ace_stage_config(optimizer, optimizer_config)
        iterations = expected_config.get("iterations", 3)
        tasks = spec["_tasks"]
        train = sum(task.split == "train" for task in tasks)
        validation = sum(task.split == "validation" for task in tasks)
        allowance = (train + validation + iterations *
                     (min(train, expected_config.get("batch_size", train)) + validation))
        minimum = validation + (0 if optimizer == "baseline" else allowance)
        expected_editable = (*source.editable, *((ACE_SCAFFOLD,) if optimizer == "meta_harness" else ()))
        expected_build = (("python3", "-c", SCAFFOLD_CALL, f"agent/{ACE_SCAFFOLD}", "task")
                          if optimizer == "meta_harness" else ())
        expected_stage = ({} if optimizer == "baseline" else
                           {"id": optimizer, "optimizer": optimizer, "inputs": ["baseline"],
                            "max_trials": allowance, "config": expected_config})
        expected_seed = ({ACE_SCAFFOLD: spec["_source"].parent.relative_to(root).as_posix()
                          + "/ace_scaffold.py"} if optimizer == "meta_harness" else {})
        valid = (
            choice == {"agent": "ace-rtl", "harness": "ace-opencode",
                       "optimizer": optimizer, "dataset": "cvdp"}
            and optimizer in {"gepa", "meta_harness", "baseline"}
            and spec["_source"].is_relative_to(root / "runs/configs")
            and source.source.kind == "git"
            and source.source.revision == "fead921f18bb57345b5a41ef93ba625be208e99c"
            and profile.get("adapter") == "ace_opencode"
            and profile.get("id") == "ace-opencode"
            and profile.get("model_env") == "AGENT_OPT_MODEL"
            and profile.get("runtime", {}).get("kind") == "docker"
            and profile["runtime"].get("network") == "bridge"
            and {"AGENT_OPT_MODEL", "AGENT_OPT_MODEL_API_KEY", "OPENCODE_CONFIG"}.issubset(
                profile["runtime"].get("env_passthrough", []))
            and len(spec["_agents"]) == len(spec["_profiles"]) == 1
            and agent.id == source.id and agent.source == source.source
            and agent.prompt_file == source.prompt_file
            and agent.supported_harnesses == source.supported_harnesses
            and agent.editable == expected_editable and agent.build == expected_build
            and spec["_profiles"][0] == profile
            and spec["agents"] == [template["agents"][0] if optimizer != "meta_harness"
                                   else spec["_source"].parent.relative_to(root).as_posix() + "/agent.toml"]
            and spec["harnesses"] == template["harnesses"]
            and spec["benchmark"] == template["benchmark"] and spec["evaluator"] == "cvdp"
            and spec.get("candidate_seed_files", {}) == expected_seed
            and (optimizer != "meta_harness" or
                 safe_path(root, expected_seed[ACE_SCAFFOLD]).read_bytes()
                 == Path(__file__).with_name("ace_scaffold.py").read_bytes())
            and spec["plugins"] == {"harnesses": template["plugins"]["harnesses"]}
            and type(spec["budget"]["max_trials"]) is int
            and spec["budget"]["max_trials"] >= minimum
            and type(spec["budget"]["trial_timeout_seconds"]) in {int, float}
            and type(spec["budget"]["max_wall_time_seconds"]) in {int, float}
            and math.isfinite(spec["budget"]["trial_timeout_seconds"])
            and math.isfinite(spec["budget"]["max_wall_time_seconds"])
            and spec["budget"]["trial_timeout_seconds"] > 0
            and spec["budget"]["max_wall_time_seconds"] > 0
            and spec.get("final_test") is False
            and spec.get("final_stages") == (["baseline"] if optimizer == "baseline" else [optimizer])
            and spec.get("stages", []) == ([] if optimizer == "baseline" else [expected_stage])
            and spec["objective"] == {"mode": "lexicographic", "keep": 1, "metrics": [
                {"name": "solve_rate", "source": "passed", "direction": "maximize", "aggregate": "mean"}]}
            and spec.get("output_dir") == "runs" and spec.get("repetitions", 1) == 1
            and "pairs" not in spec and "plugin_dependencies" not in spec
            and spec.get("evaluator_config") == {"repo": str(root / "external/cvdp_benchmark"),
                                                  "python": str(root / "external/cvdp-venv/bin/python")}
        )
    except (ConfigurationError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        valid = False
    if not valid:
        raise ConfigurationError("ACE 선택형 설정의 구성요소가 일치하지 않습니다")


def _lifecycle(root: Path):
    path = root / "examples/ace-rtl/environment/lifecycle.py"
    spec = importlib.util.spec_from_file_location("ace_selected_preset_lifecycle", path)
    if spec is None or spec.loader is None:
        raise ConfigurationError("ACE 고정 lifecycle 파일을 확인할 수 없습니다")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_ace_selection(root: Path, *, offline: bool = False) -> None:
    """확인 후 검증된 고정 연동 자산만 준비한다."""
    from agent_optimizer.registry import is_source_checkout
    if is_source_checkout(root):
        _lifecycle(root).prepare(root, offline=offline)
    else:
        from agent_optimizer.integrations import prepare_pointer, write_pending_experiment
        pointer = root / "experiment.toml"
        if not pointer.exists():
            pointer = write_pending_experiment(root, "ace-rtl")
        prepare_pointer(pointer, offline=offline)


def execute_ace_selection(experiment: Path, *, on_event=None) -> tuple[Path, dict]:
    """선택된 TOML을 검증·고정 평가 lock·runner에 연결한다."""
    from agent_optimizer.model_input import session_environment
    from agent_optimizer.models import ModelSettings
    from agent_optimizer.network import demo_environment, network_environment
    from agent_optimizer.readiness import collect_plan
    from agent_optimizer.runner import run_experiment

    spec = load_experiment(experiment)
    verify_ace_selection(spec)
    root = spec["_root"]
    if not is_source_checkout(root):
        from agent_optimizer.integrations import resolve_pointer
        pointer = root / "experiment.toml"
        if not pointer.is_file():
            raise UnavailableError("ACE 고정 연동 준비가 필요합니다")
        resolve_pointer(pointer)
    model = os.environ.get("AGENT_OPT_MODEL", "")
    if model.startswith("compatible/"):
        settings = ModelSettings.from_env()
        if model != "compatible/" + settings.model:
            raise ConfigurationError("ACE compatible 모델 선택자는 AGENT_OPT_MODEL_ID와 일치해야 합니다")
        opencode_config = "/opt/agent-optimizer/compatible.json"
    elif model.startswith("openrouter/"):
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise UnavailableError("ACE OpenRouter 모델에는 OPENROUTER_API_KEY가 필요합니다")
        opencode_config = "/opt/agent-optimizer/opencode.json"
    else:
        raise ConfigurationError("ACE OpenCode 모델은 compatible/모델 또는 openrouter/모델을 선택하세요")
    inspection = _lifecycle(root).inspect(root)
    if not inspection["ready"]:
        failures = [item["id"] for item in inspection["checks"]
                    if item["area"] == "evaluation" and item["status"] != "ok"]
        raise ConfigurationError("ACE 평가 환경 준비 부족: " + ", ".join(failures))
    environment = {**os.environ, **demo_environment(), **network_environment(),
                   "OPENCODE_CONFIG": opencode_config,
                   "DOCKER_DEFAULT_PLATFORM": inspection["platform"],
                   "OSS_SIM_IMAGE": inspection["sim_image"]}
    with session_environment(environment):
        diagnosis = collect_plan(experiment, Registry())
        if not diagnosis["ready"]:
            failures = [item["id"] for item in diagnosis["checks"] if item["status"] != "ok"]
            raise ConfigurationError("선택한 실험의 정적 계획 진단 실패: " + ", ".join(failures))
        for profile in spec["_profiles"]:
            if profile.get("runtime", {}).get("kind") == "docker":
                profile["runtime"]["image"] = inspection["lock"]["images"]["agent"]["id"]
        run_dir, summary = run_experiment(spec, Registry(), on_event=on_event)
    return run_dir, summary


def run_ace_selection(experiment: Path) -> int:
    """비대화형 CLI의 기존 출력·종료 코드 유지."""
    from agent_optimizer.cli import next_command, show
    from agent_optimizer.terminal_report import ProgressDisplay

    with ProgressDisplay() as progress:
        progress.configure_budget(load_experiment(experiment)["budget"]["max_trials"])
        run_dir, summary = execute_ace_selection(experiment, on_event=progress)
    show({"run_dir": run_dir, "status": summary["status"], "trials_used": summary["trials_used"],
          "report_html": run_dir / "report.html"})
    print(f"결과 HTML: {run_dir / 'report.html'}", file=sys.stderr)
    next_command(f"agent-opt report {run_dir}")
    return 0 if summary["status"] == "completed" else 3
