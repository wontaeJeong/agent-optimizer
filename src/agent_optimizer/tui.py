"""Textual interactive front end; the CLI and this app call the same experiment functions."""
from __future__ import annotations

import os
import io
import contextlib
import traceback
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.locale import human, render_diagnostic
from agent_optimizer.preset_tui import ACE_GUIDANCE, ACE_SCAFFOLD, _tr, preset_options
from agent_optimizer.registry import is_source_checkout


STEPS = ("Agent", "Harness", "Optimizer", "Dataset")


def _name(page: str) -> str:
    return {"Home": _tr("시작", "Home"), "Review": _tr("실행 전 확인", "Review"),
            "History": _tr("이전 실행", "Run History"),
            "Existing": _tr("기존 실험", "Existing Experiment"),
            "Workspace": _tr("ACE 작업공간", "ACE workspace"),
            "Advanced": _tr("고급 설정", "Advanced Setup"),
            "Model": _tr("모델 설정", "Model settings"),
            "Running": _tr("실행 상태", "Run status"), **{
                step: step for step in STEPS}}[page]


class OptimizerApp(App[int]):
    TITLE = "Agent Optimizer"
    BINDINGS = [Binding("escape", "back", "Esc Back", priority=True),
                Binding("q", "quit_app", "q Quit"),
                Binding("ctrl+c", "quit_app", "Quit", show=False)]
    CSS = """
    Screen { background: $surface; }
    #path { height: 3; padding: 1 2; color: $accent; text-style: bold; }
    #columns { height: 1fr; }
    #options { width: 36%; min-width: 25; height: 1fr; border: round $accent; }
    #details-panel { width: 1fr; height: 1fr; border: round $primary; padding: 1 2; }
    #details { width: 1fr; height: 1fr; overflow-y: auto; }
    #review-panel { display: none; height: 1fr; border: round $primary; padding: 1 2; }
    #review { width: 100%; height: auto; text-wrap: wrap; }
    #entry { display: none; margin: 0 1; }
    #hint { height: 2; padding: 0 2; color: $text-muted; }
    .narrow #columns { layout: vertical; }
    .narrow #options { width: 100%; min-width: 0; height: 45%; }
    .narrow #details-panel { width: 100%; height: 55%; }
    .reviewing #columns { height: 5; }
    .reviewing #options { width: 100%; height: 1fr; }
    .reviewing #details-panel { display: none; }
    """

    def __init__(self, project_root: Path):
        super().__init__()
        self.root = project_root.absolute()
        self.page = "Agent"
        self.selections: dict[str, str] = {}
        self.focus_indices: dict[str, int] = {}
        self.rows: list[tuple] = []
        self.experiment: Path | None = None
        self.workspace = self.root
        self.history: list[tuple[str, str, int, Path]] = []
        self.return_page = "Home"
        self.workspace_back = "Home"
        self.model_values: dict[str, str] = {}
        self.model_fields: list[str] = []
        self.model_index = 0
        self.busy = False
        self.outcome = 0

    def compose(self) -> ComposeResult:
        yield Static(id="path")
        with Horizontal(id="columns"):
            yield OptionList(id="options")
            with Vertical(id="details-panel"):
                yield Static(id="details")
        with VerticalScroll(id="review-panel"):
            yield Static(id="review")
        yield Input(id="entry")
        yield Static(id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#options", OptionList).border_title = _tr("선택지", "Options")
        self.query_one("#details-panel").border_title = _tr("상세", "Details")
        self._show("Agent")

    def on_resize(self, event: Resize) -> None:
        self.set_class(event.size.width < 76, "narrow")

    def _show(self, page: str) -> None:
        self.page = page
        self.set_class(page == "Review", "reviewing")
        options = self.query_one("#options", OptionList)
        entry = self.query_one("#entry", Input)
        review = self.query_one("#review", Static)
        self.query_one("#path", Static).update(self._breadcrumb())
        self.query_one("#hint", Static).update(
            _tr("↑↓ 탐색 · Enter 선택 · Esc 이전 · q 종료 · Tab 확인 내용 스크롤",
                "↑↓ Navigate · Enter Select · Esc Back · q Quit · Tab scroll review")
            if page == "Review" else _tr(
                "↑↓ 탐색 · Enter 선택 · Esc 이전 · q 종료 · Tab 입력/목록 전환",
                "↑↓ Navigate · Enter Select · Esc Back · q Quit · Tab switch input/list"))
        entry.styles.display = "none"
        self.query_one("#review-panel").styles.display = "none"
        self.query_one("#columns").styles.display = "block"
        self.rows = []
        if page == "Home":
            self.rows = [(_tr("새 최적화", "New Optimization"),
                          _tr("Agent부터 차례대로 선택합니다.", "Select Agent, Harness, Optimizer, Dataset, then review."), True),
                         (_tr("기존 실험", "Existing Experiment"),
                          _tr("experiment.toml을 선택하고 진단 후 실행합니다.", "Choose an experiment.toml, check it, then run."), True),
                         (_tr("이전 실행", "Run History"),
                          _tr("저장된 실행과 보고서 경로를 확인합니다.", "Inspect stored runs and report paths."), True),
                         (_tr("고급 설정", "Advanced Setup"),
                          _tr("맞춤 Agent·Harness·Optimizer·Dataset에는 agent-opt init을 사용합니다.",
                              "Use agent-opt init for custom Agent, Harness, Optimizer or Dataset."), True),
                         (_tr("ACE 예제", "ACE example"),
                          _tr("별도 ACE 작업공간에서 고정 연동을 준비합니다.",
                              "Prepare the pinned integration in an ACE workspace."), True),
                         (_tr("종료", "Quit"), _tr("앱을 종료합니다.", "Exit the app."), True)]
        elif page in STEPS:
            self.rows = preset_options(self.root, page, self.selections.get("Agent", "ace-rtl"))
        elif page == "Existing":
            from agent_optimizer.cli import _recent_configurations
            recent = _recent_configurations(self.root)
            self.rows = [(str(path), _tr("최근 생성된 설정 · 선택하면 실행 전 확인으로 이동",
                                          "Recent generated configuration · review before running"), True)
                         for path in recent]
            self.rows.append((_tr("경로 직접 입력", "Enter a path"),
                              _tr("아래에 experiment.toml 경로를 입력하세요.",
                                  "Enter an experiment.toml path below."), True))
            entry.placeholder = _tr("기존 experiment.toml 경로", "Path to existing experiment.toml")
            entry.value = ""
            entry.styles.display = "block"
        elif page == "History":
            from agent_optimizer.cli import recent_runs
            self.history = recent_runs(self.root)
            self.rows = [(f"{name} · {status}",
                          f"{_tr('생성', 'Created')}: {name[:15]} UTC\n"
                          f"{_tr('상태', 'Status')}: {status}\n"
                          f"{_tr('시도', 'Trials')}: {trials}\n"
                          f"{_tr('보고서', 'Report')}: {report}\n"
                          + _tr("Enter: 저장된 보고서 경로 확인 (다시 검증)",
                                "Enter: verify the stored report path again"), True)
                         for name, status, trials, report in self.history]
        elif page == "Review":
            self.rows = [(_tr("준비하고 실행", "Prepare and Run"),
                          _tr("진단을 통과한 뒤에만 실행합니다.", "Run only after readiness checks pass."), True),
                         (_tr("취소", "Cancel"), _tr("자산 준비나 설정 파일을 만들지 않고 돌아갑니다.",
                                                "Return without preparing assets or writing a configuration."), True)]
            self.query_one("#review-panel").styles.display = "block"
            review.update(self._review())
        elif page == "Advanced":
            self.rows = [(_tr("기존 설정 선택", "Select existing config"),
                          _tr("agent-opt init으로 생성한 설정을 실행합니다.", "Run a configuration created by agent-opt init."), True)]
        elif page == "Workspace":
            entry.placeholder = _tr("ACE-RTL 작업공간 경로", "ACE-RTL workspace path")
            entry.value = "" if self.workspace == self.root else str(self.workspace)
            entry.styles.display = "block"
            self.rows = [(_tr("작업공간 선택", "Select workspace"),
                          _tr("고정 Git·CVDP·driver·Docker 자산은 실행 확인 뒤 준비합니다.",
                              "Pinned Git, CVDP, driver and Docker assets are prepared after review."), True)]
        elif page == "Model":
            field = self.model_fields[self.model_index]
            entry.placeholder = f"{field} ({_tr('입력 후 Enter', 'type and press Enter')})"
            entry.value = self.model_values.get(field, "")
            entry.password = field.endswith("KEY")
            entry.styles.display = "block"
            self.rows = [(field, _tr("이 값은 이번 실행에만 적용됩니다. 비밀 값은 표시하지 않습니다.",
                                     "Session-only value; secrets remain hidden."), True)]
        elif page == "Running":
            self.rows = [(_tr("진행", "Progress"), _tr("작업이 끝나면 보고서 경로를 표시합니다.",
                                                    "The report path appears when the work finishes."), True)]
        options.set_options([Option(Text(row[0] + ("  ×" if not row[2] else ""),
                                        style="" if row[2] else "dim")) for row in self.rows])
        index = min(self.focus_indices.get(page, 0), len(self.rows) - 1)
        options.highlighted = index
        self._detail(index)
        if page in {"Existing", "Workspace", "Model"}:
            entry.focus()
        else:
            options.focus()

    def _breadcrumb(self) -> str:
        past = " / ".join(f"{step}: {self.selections[step]}" for step in STEPS
                          if step in self.selections and step != self.page)
        return f"Agent Optimizer  /  {_name(self.page)}" + (f"  ·  {past}" if past else "")

    def _detail(self, index: int | None) -> None:
        if index is None or not 0 <= index < len(self.rows):
            self.query_one("#details", Static).update(_tr("표시할 항목이 없습니다.", "No items to show."))
            return
        row = self.rows[index]
        status = row[3] if len(row) > 3 else _tr("사용 가능", "Available") if row[2] else _tr("선택 불가", "Unavailable")
        next_step = (STEPS[STEPS.index(self.page) + 1] if self.page in STEPS[:-1] else
                     "Review" if self.page == "Dataset" else "")
        detail = f"{row[0]}\n\n{row[1]}\n\n{_tr('상태', 'Status')}: {status}"
        if not row[2]:
            detail += "\n" + _tr("이 조합은 선택할 수 없습니다. 기존 실험 또는 고급 설정을 이용하세요.",
                                   "This combination cannot be selected. Use an existing experiment or advanced setup.")
        if next_step:
            detail += f"\n\n{_tr('다음', 'Next')}: {next_step}"
        if self.page == "Advanced":
            detail += "\n\nagent-opt init\nagent-opt init --help"
        self.query_one("#details", Static).update(detail)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.focus_indices[self.page] = event.option_index
        self._detail(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index >= len(self.rows) or not self.rows[event.option_index][2]:
            return
        index = event.option_index
        if self.page == "Home":
            if index == 0:
                self.experiment = None
                self.workspace = self.root
                self.selections.clear()
                self._show("Agent")
            elif index == 1:
                self._show("Existing")
            elif index == 2:
                self._show("History")
            elif index == 3:
                self._show("Advanced")
            elif index == 4:
                self.experiment = None
                self.workspace_back = "Home"
                self.return_page = "Home"
                self._show("Workspace")
            else:
                self.exit(0)
        elif self.page in STEPS:
            if self.page == "Agent" and index >= len(self.rows) - 2:
                self._show("Advanced" if index == len(self.rows) - 2 else "Existing")
                return
            if self.page != "Agent" and index >= len(self.rows) - (2 if self.page != "Dataset" else 2):
                self._show("Advanced" if index == len(self.rows) - 2 else "Existing")
                return
            key = self.rows[index][0]
            value = ({"ACE-RTL": "ace-rtl"}.get(key, key) if self.page == "Agent" else
                     {"OpenCode": "ace-opencode", "Fixture": "fixture", "GEPA": "gepa",
                      "Meta-Harness": "meta_harness", "Baseline": "baseline",
                      "FileVariants": "file_variants", "CVDP": "cvdp"}.get(key, key))
            if self.selections.get(self.page) != value:
                for step in STEPS[STEPS.index(self.page) + 1:]:
                    self.selections.pop(step, None)
                    self.focus_indices.pop(step, None)
            self.selections[self.page] = value
            next_page = "Review" if self.page == "Dataset" else STEPS[STEPS.index(self.page) + 1]
            self.return_page = "Dataset"
            if next_page == "Review" and value == "cvdp" and not is_source_checkout(self.root):
                next_page = "Workspace"
                self.workspace_back = "Dataset"
            self._show(next_page)
        elif self.page == "Existing":
            if index == len(self.rows) - 1:
                self.query_one(Input).focus()
            else:
                self._load_existing(Path(self.rows[index][0]))
        elif self.page == "History":
            from agent_optimizer.cli import verified_run_report
            try:
                report = verified_run_report(self.root, self.history[index][3], self.history[index][1])
                self.query_one("#details", Static).update(
                    f"{_tr('보고서 경로', 'Report path')}: {report}")
            except ConfigurationError as exc:
                self._error(exc)
        elif self.page == "Review":
            if index == 0:
                self._start()
            else:
                self._show(self.return_page)
        elif self.page == "Advanced":
            self._show("Existing")
        elif self.page in {"Workspace", "Model"}:
            self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if self.page == "Existing":
            if not value:
                self._error(ConfigurationError(_tr("실험 설정 경로를 입력하세요", "Enter a configuration path")))
                return
            path = Path(value).expanduser()
            self._load_existing(path if path.is_absolute() else self.root / path)
        elif self.page == "Workspace":
            if not value:
                self._error(ConfigurationError(_tr("ACE 작업공간 경로를 입력하세요", "Enter an ACE workspace path")))
                return
            path = Path(value).expanduser()
            self.workspace = path.absolute() if path.is_absolute() else (self.root / path).absolute()
            self.selections = {"Agent": "ace-rtl", "Harness": "ace-opencode",
                               "Optimizer": "gepa", "Dataset": "cvdp"}
            self.return_page = "Workspace"
            self._show("Review")
        elif self.page == "Model":
            field = self.model_fields[self.model_index]
            if not value:
                self._error(ConfigurationError(f"{field}: {_tr('값을 입력하세요', 'value required')}"))
                return
            self.model_values[field] = value
            self.model_fields = self._missing_model_fields()
            if self.model_fields:
                self.model_index = 0
                self._show("Model")
            else:
                self._run()

    def _load_existing(self, path: Path) -> None:
        try:
            spec = load_experiment(path.resolve())
        except (ConfigurationError, OSError, ValueError, KeyError, TypeError) as exc:
            self._error(exc)
            return
        self.experiment = spec["_source"]
        self.return_page = "Existing"
        self._show("Review")

    def _review(self) -> str:
        if self.experiment is not None:
            try:
                spec = load_experiment(self.experiment)
                budget = spec["budget"]
                rows = [f"{_tr('설정', 'Configuration')}: {self.experiment}",
                        f"Agent: {', '.join(a.id for a in spec['_agents'])}",
                        f"Harness: {', '.join(p['id'] for p in spec['_profiles'])}",
                        f"Optimizer: {', '.join(s['optimizer'] for s in spec['stages']) or 'baseline'}",
                        f"Dataset: {spec.get('benchmark')}"]
            except (ConfigurationError, OSError, KeyError, TypeError) as exc:
                return str(exc)
        else:
            ace = self.selections.get("Agent") == "ace-rtl"
            optimizer = self.selections.get("Optimizer", "gepa")
            maximum = (1 if optimizer == "baseline" else 9) if ace else (4 if optimizer == "file_variants" else 3)
            timeout = 600 if ace else 120
            budget = {"max_trials": maximum, "trial_timeout_seconds": timeout,
                      "max_wall_time_seconds": (maximum * timeout + 360 if ace else 3600)}
            editable = (ACE_GUIDANCE if optimizer == "gepa" else ACE_SCAFFOLD if optimizer == "meta_harness"
                        else "configs/strategy.json" if optimizer == "file_variants" else _tr("변경 없음", "No changes"))
            rows = [f"{step}: {self.selections.get(step, '-')}" for step in STEPS]
            rows += [f"{_tr('수정 대상', 'Active edit')}: {editable}",
                     f"{_tr('준비', 'Preparation')}: " + (_tr("고정 Git·CVDP·driver·Docker 자산", "Pinned Git, CVDP, driver, Docker assets")
                                                    if ace else _tr("로컬 합성 fixture 검사", "Check local synthetic fixture")),
                     f"{_tr('작업공간', 'Workspace')}: {'.' if self.workspace == self.root else self.workspace}",
                     f"{_tr('설정', 'Configuration')}: runs/configs/<new-config>/experiment.toml",
                     f"{_tr('평가', 'Evaluation')}: " + ("cvdp · train 1 / validation 1 · final_test=false" if ace else
                                                    "sample_eval · synthetic train / validation / test")]
            if ace:
                model = self.model_values.get("AGENT_OPT_MODEL") or os.environ.get("AGENT_OPT_MODEL", "")
                rows += [f"{_tr('Agent 모델', 'Agent model')}: {model or _tr('입력 필요', 'input needed')}",
                         f"{_tr('Optimizer 모델', 'Optimizer model')}: " + (
                             _tr("필요 없음", "not needed") if optimizer == "baseline" else
                             " · ".join(f"{label} " + (_tr("설정", "set") if self.model_values.get(key) or os.environ.get(key)
                                                      else _tr("필요", "needed"))
                                        for label, key in (("URL", "AGENT_OPT_MODEL_BASE_URL"),
                                                           ("ID", "AGENT_OPT_MODEL_ID"),
                                                           ("API key", "AGENT_OPT_MODEL_API_KEY"))))]
                if model.startswith("openrouter/"):
                    rows.append("OPENROUTER_API_KEY: " + (_tr("설정됨", "configured") if
                                self.model_values.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
                                else _tr("입력 필요", "input needed")))
        rows += [f"{_tr('최대 시도', 'Trials')}: {budget['max_trials']}",
                 f"{_tr('시도 시간제한', 'Trial timeout')}: {budget['trial_timeout_seconds']}s",
                 f"{_tr('전체 시간제한', 'Wall time')}: {budget['max_wall_time_seconds']}s",
                 f"{_tr('보고서', 'Report')}: " + (
                     'runs/<run-id>/report.html' if self.experiment is None else
                     str(spec['_root'] / spec.get('output_dir', 'runs') / '<run-id>/report.html')),
                 "", _tr("Enter: 준비·진단 후 실행   Esc: 뒤로", "Enter: prepare, check, run   Esc: back")]
        return "\n".join(rows)

    def _missing_model_fields(self) -> list[str]:
        values = {**os.environ, **self.model_values}
        if self.experiment:
            spec = load_experiment(self.experiment)
            profiles = spec["_profiles"]
            research = any(s["optimizer"] in {"gepa", "meta_harness", "ecdysis"} for s in spec["stages"])
            selectors = [p.get("model_env", "AGENT_OPT_MODEL") for p in profiles
                         if p["adapter"] == "opencode" or p["adapter"] == "ace_opencode"
                         and spec.get("preset_selection")]
            api = research or any(p["adapter"] not in {"opencode", "ace_opencode"} and
                                  {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"}.issubset(
                                      p.get("runtime", {}).get("env_passthrough", [])) or
                                  p["adapter"] == "ace_opencode" and not spec.get("preset_selection") and
                                  {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"}.issubset(
                                      p.get("runtime", {}).get("env_passthrough", []))
                                  for p in profiles)
        else:
            selectors = ["AGENT_OPT_MODEL"] if self.selections.get("Agent") == "ace-rtl" else []
            api = self.selections.get("Agent") == "ace-rtl" and self.selections.get("Optimizer") != "baseline"
        fields = list(dict.fromkeys(selectors))
        if any(values.get(key) and (values[key].startswith("compatible/") or "/" not in values[key])
               for key in selectors):
            api = True
        if any(values.get(key, "").startswith("openrouter/") for key in selectors):
            fields.append("OPENROUTER_API_KEY")
        if api:
            fields += ["AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY"]
        return [key for key in dict.fromkeys(fields) if not values.get(key)]

    def _start(self) -> None:
        try:
            fields = self._missing_model_fields()
        except (ConfigurationError, OSError) as exc:
            self._error(exc)
            return
        if fields:
            self.model_fields = fields
            self.model_index = 0
            self._show("Model")
        else:
            self._run()

    def _run(self) -> None:
        self.outcome = 0
        self.busy = True
        self._show("Running")
        self._status(_tr("Preparing · 선택한 자산과 설정을 확인합니다…",
                         "Preparing · checking selected assets and configuration…"))
        self.execute()

    def _status(self, text: str) -> None:
        self.query_one("#details", Static).update(text)

    @work(thread=True, exclusive=True)
    def execute(self) -> None:
        from agent_optimizer.cli import _launch_existing
        from agent_optimizer.model_input import session_environment
        from agent_optimizer.preset_tui import (execute_ace_selection, prepare_ace_selection,
                                                write_ace_selection, write_sample_selection)
        from agent_optimizer.readiness import collect_plan
        from agent_optimizer.registry import Registry
        from agent_optimizer.runner import run_experiment
        from agent_optimizer.models import ModelSettings

        try:
            values = {**os.environ, **self.model_values}
            if self.selections.get("Agent") == "ace-rtl" or self.experiment:
                if values.get("AGENT_OPT_MODEL_BASE_URL") and values.get("AGENT_OPT_MODEL_API_KEY"):
                    ModelSettings.from_env(values)
                selector = values.get("AGENT_OPT_MODEL", "")
                if selector and "/" not in selector:
                    if values.get("AGENT_OPT_MODEL_ID") not in {None, "", selector}:
                        raise ConfigurationError("AGENT_OPT_MODEL_ID와 AGENT_OPT_MODEL이 일치해야 합니다")
                    values["AGENT_OPT_MODEL_ID"] = selector
                    values["AGENT_OPT_MODEL"] = "compatible/" + selector
                if values.get("AGENT_OPT_MODEL", "").startswith("compatible/") and (
                        values["AGENT_OPT_MODEL"].split("/", 1)[1] != values.get("AGENT_OPT_MODEL_ID")):
                    raise ConfigurationError("ACE compatible 모델 선택자는 AGENT_OPT_MODEL_ID와 일치해야 합니다")
            with session_environment(values):
                if self.experiment is not None:
                    experiment = self.experiment
                elif self.selections["Agent"] == "ace-rtl":
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        prepare_ace_selection(self.workspace)
                    experiment = write_ace_selection(self.workspace, self.selections["Optimizer"])
                else:
                    experiment = write_sample_selection(self.workspace, self.selections["Agent"],
                                                        self.selections["Optimizer"], progress_stream=io.StringIO())
                self.call_from_thread(self._status, f"{_tr('Checking · 정적 계획 진단', 'Checking · static plan')}: {experiment}")
                report = collect_plan(experiment, Registry())
                if not report["ready"]:
                    details = [f"{row['id']}: {' · '.join(filter(None, render_diagnostic(row)))}"
                               for row in report["checks"] if row["status"] != "ok"]
                    raise ConfigurationError("\n".join(details))
                spec = load_experiment(experiment)
                self.call_from_thread(self._status, _tr("Running · 평가 이벤트를 기다립니다…",
                                                        "Running · waiting for evaluation events…"))
                def on_event(event):
                    if event.get("event") in {"trial_started", "trial_completed", "optimizer_iteration_started", "error"}:
                        self.call_from_thread(self._status,
                            f"{_tr('실행 중', 'Running')}: {event.get('stage_id', '-')} · "
                            f"{event.get('task_id', '-')} · {event['event']}")
                launched = _launch_existing(spec, Registry())
                if launched is not None:
                    self.outcome = launched
                    result = f"{_tr('전용 프로필 종료 코드', 'Dedicated profile exit code')}: {launched}"
                else:
                    if spec.get("preset_selection"):
                        run_dir, summary = execute_ace_selection(experiment, on_event=on_event)
                    else:
                        run_dir, summary = run_experiment(spec, Registry(), on_event=on_event)
                    result = (f"{_tr('완료', 'Completed') if summary['status'] == 'completed' else _tr('실패', 'Failed')}: "
                              f"{summary['status']}\n{_tr('시도', 'Trials')}: {summary['trials_used']}\n"
                              f"{_tr('보고서', 'Report')}: {run_dir / 'report.html'}")
                    self.outcome = 0 if summary["status"] == "completed" else 3
                self.call_from_thread(self._finish, result)
        except (ConfigurationError, UnavailableError, OSError, ValueError, KeyError, TypeError) as exc:
            self.outcome = 2
            self.call_from_thread(self._finish, f"{_tr('설정/준비 오류', 'Configuration / readiness error')}\n\n"
                                  f"{human(str(exc))}\n\n{_tr('다음 작업: 선택한 설정·자산·모델을 확인하세요.', 'Next: check the selected configuration, assets and model.')}")
        except Exception as exc:
            self.outcome = 2
            self.log.error(traceback.format_exc())
            self.call_from_thread(self._finish, f"{_tr('내부 오류', 'Internal error')}: {exc}\n"
                                  + _tr("상세 traceback은 Textual 로그에서 확인하세요.",
                                        "See the Textual log for the traceback."))

    def _finish(self, text: str) -> None:
        self.busy = False
        self._status(text + "\n\n" + _tr("Esc: 돌아가기 · q: 종료", "Esc: back · q: quit"))

    def _error(self, exc: Exception) -> None:
        self.query_one("#details", Static).update(
            f"{_tr('설정 오류', 'Configuration Error')}\n\n{human(str(exc))}\n\n"
            + _tr("경로·선택 항목을 확인한 뒤 다시 시도하세요.", "Check the path or selection and try again."))

    def action_back(self) -> None:
        if self.busy:
            self.notify(_tr("실행 중입니다. 완료 후 결과를 확인하세요.", "Running; wait for the result."))
            return
        if self.page in STEPS:
            self._show("Home" if self.page == "Agent" else STEPS[STEPS.index(self.page) - 1])
        elif self.page == "Review":
            self._show(self.return_page)
        elif self.page == "Model":
            self.model_values.clear()
            self._show("Review")
        elif self.page == "Running":
            self._show("Home")
        elif self.page == "Workspace":
            self._show(self.workspace_back)
        else:
            self._show("Home")

    def action_quit_app(self) -> None:
        if self.busy:
            self.notify(_tr("실행 중입니다. 완료 후 종료하세요.", "Running; quit after completion."))
        else:
            self.exit(self.outcome)
