"""Textual interactive front end; the CLI and this app call the same experiment functions."""
from __future__ import annotations

import os
import json
import shlex
import contextlib
import math
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import unquote, unquote_plus, urlsplit

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize
from textual.message import Message
from textual.widgets import Footer, Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.locale import human, render_diagnostic
from agent_optimizer.models import DEFAULT_MODEL_ID, ModelSettings
from agent_optimizer.preset_tui import ACE_GUIDANCE, ACE_SCAFFOLD, ChoiceRow, _tr, preset_options
from agent_optimizer.registry import is_source_checkout
from agent_optimizer.terminal_report import ProgressState, format_progress_event


STEPS = ("Agent", "Harness", "Optimizer", "Dataset")


def endpoint_contains_credentials(value: str) -> bool:
    """Reject unambiguous credential syntax, including unfinished user:password input."""
    if "?" in value or "#" in value:
        return True
    authority = value.split("://", 1)[-1].split("/", 1)[0]
    if "@" in authority:
        return True
    if "://" not in value:
        return False
    if authority.startswith("["):
        if "]" not in authority:
            return False  # An unfinished IPv6 host is not a credential.
        authority = authority.split("]", 1)[1]
    _host, separator, port = authority.partition(":")
    return bool(separator and port and not port.isdecimal())


class ModelInput(Input):
    """Filter secret URLs before reactive storage, rendering, or Changed messages."""

    endpoint_mode = False
    endpoint_rejected = False

    class EndpointRejected(Message):
        """Contains no rejected value, so message repr/logs cannot expose credentials."""

    def validate_value(self, value: str) -> str:
        if self.endpoint_mode:
            if endpoint_contains_credentials(value):
                self.endpoint_rejected = True
                self.post_message(self.EndpointRejected())
                return ""
            if self.endpoint_rejected and value and "://" not in value:
                return ""  # Discard the remainder of a rejected typing/paste operation.
            if value:
                self.endpoint_rejected = False
        return value


class ModelValues(dict):
    """Keep credentials in session memory without exposing them through repr."""

    def __repr__(self):
        return repr({name: "<설정됨>" if any(marker in name.upper() for marker in
                    ("KEY", "TOKEN", "SECRET", "PASSWORD")) else
                    display_endpoint(value) if name in {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ENDPOINT"} and value else value
                    for name, value in self.items()})


def validate_endpoint(value: str) -> None:
    """Use the transport contract and additionally reject invalid ports and paths."""
    try:
        parts = urlsplit(value)
        port = parts.port
        if (port == 0 or parts.netloc.endswith(":") or "\\" in value or
                "@" in parts.netloc or "?" in value or "#" in value):
            raise ValueError()
        if any(part in {".", ".."} for part in unquote(parts.path).split("/")):
            raise ValueError()
        ModelSettings.from_env({"AGENT_OPT_MODEL_BASE_URL": value,
                                "AGENT_OPT_MODEL_ID": "validation",
                                "AGENT_OPT_MODEL_API_KEY": "validation"})
    except (ValueError, ConfigurationError, UnavailableError):
        raise ConfigurationError(
            "API 주소는 HTTPS(로컬 loopback만 HTTP), 유효한 host·포트·경로를 사용하세요. "
            "자격증명·query·fragment·/chat/completions는 허용하지 않습니다.") from None


def display_endpoint(value: str) -> str:
    try:
        parts = urlsplit(value)
        if "@" in parts.netloc or "?" in value or "#" in value:
            return "자격증명 포함 URL—분리 필요"
        validate_endpoint(value)
    except (ValueError, ConfigurationError):
        return "잘못된 URL—수정 필요"
    return value


def _name(page: str) -> str:
    if page in {'Native', 'NativeRows', 'NativeSplit', 'SessionHistory'}:
        from agent_optimizer.locale import t
        return t({'Native': 'Native CID·row 선택', 'NativeRows': 'Native row 선택',
                  'NativeSplit': '선택 row의 split 지정', 'SessionHistory': '세션 개별 실행'}[page])
    return {"Home": _tr("시작", "Home"), "Review": _tr("실행 전 확인", "Review"),
            "History": _tr("이전 실행", "Run History"),
            "Existing": _tr("기존 실험", "Existing Experiment"),
            "Workspace": _tr("ACE 작업공간", "ACE workspace"),
            "Advanced": _tr("고급 설정", "Advanced Setup"),
            "Model": _tr("모델 설정", "Model Setup"),
            "Preparing": _tr("준비 중", "Preparing"),
            "Doctor": _tr("실행 전 진단", "Pre-flight checks"),
            "Result": _tr("실행 결과", "Result"),
            "Running": _tr("실행 상태", "Run status"), **{
                step: step for step in STEPS}}[page]


class PreparationLine(Message):
    def __init__(self, line: str):
        super().__init__()
        self.line = line


class _ProgressCapture:
    """Capture preparation output and forward complete lines to the Textual app."""

    def __init__(self, app):
        self.app = app
        self.pending = ""
        self.lock = threading.Lock()

    def write(self, value: str) -> int:
        with self.lock:
            self.pending += value
            lines = self.pending.split("\n")
            self.pending = lines.pop()
        for line in lines:
            if line.strip():
                self.app.post_message(PreparationLine(line.rstrip("\r")))
        return len(value)

    def flush(self) -> None:
        with self.lock:
            line, self.pending = self.pending, ""
        if line.strip():
            self.app.post_message(PreparationLine(line.rstrip("\r")))

    def isatty(self) -> bool:
        return False


class OptimizerApp(App[int]):
    TITLE = "Agent Optimizer"
    BINDINGS = [Binding("escape", "back", "Esc Back", priority=True),
                Binding("q", "quit_app", "q Quit"),
                Binding("ctrl+c", "quit_app", "Quit", show=False)]
    CSS = """
    Screen { background: $surface; }
    #path { height: 4; padding: 0 2; color: $accent; text-style: bold; }
    #home-status { height: auto; max-height: 4; padding: 0 2; color: $text-muted; }
    #columns { height: 1fr; }
    #options { width: 36%; min-width: 25; height: 1fr; border: round $accent; }
    #details-panel { width: 1fr; height: 1fr; border: round $primary; padding: 1 2; }
    #details { width: 1fr; height: auto; text-wrap: wrap; }
    #review-panel { display: none; height: 1fr; border: round $primary; padding: 1 2; }
    #review { width: 100%; height: auto; text-wrap: wrap; }
    #run-panel { display: none; height: 1fr; }
    #run-state { height: 8; min-height: 5; border: round $primary; padding: 0 1; }
    #event-log { height: 1fr; min-height: 6; border: round $accent; padding: 0 1; }
    #entry { display: none; margin: 0 1; }
    #hint { height: 2; padding: 0 2; color: $text-muted; }
    .narrow #columns { layout: vertical; }
    .narrow #options { width: 100%; min-width: 0; height: 45%; }
    .narrow #details-panel { width: 100%; height: 55%; }
    .reviewing #columns { height: 5; }
    .reviewing #options { width: 100%; height: 1fr; }
    .reviewing #details-panel { display: none; }
    .narrow #run-state { height: 7; min-height: 5; }
    .narrow #event-log { height: 1fr; min-height: 6; }
    """

    def __init__(self, project_root: Path):
        super().__init__()
        self.root = project_root.absolute()
        self.page = "Home"
        self.home_status = ""
        self.selections: dict[str, str] = {}
        self.focus_indices: dict[str, int] = {}
        self.rows: list[ChoiceRow] = []
        self.focus_ids: dict[str, str] = {}
        self.input_drafts = ModelValues()
        self.experiment: Path | None = None
        self.workspace = self.root
        self.history: list[dict] = []
        self._report_lock = threading.Lock()
        self._report_handle = None
        self._report_path = None
        self._report_epoch = 0
        self._report_closing = False
        self.native_values = {}
        self.native_field = 'cids'
        self.return_page = "Home"
        self.workspace_back = "Home"
        self.model_values: dict[str, str] = ModelValues()
        self.model_presets: dict[str, dict[str, str]] = {}
        self.component_metadata: dict[str, dict] = {}
        from agent_optimizer.catalog import describe_choice
        self.component_metadata['ace-native'] = describe_choice('harness', 'ace-native', self.root)
        self.model_sources: dict[str, str] = {}
        self.model_fields: list[str] = []
        self.model_index = 0
        self.model_mode = "fields"
        self.model_field = ""
        self.model_return_page = "Review"
        self.busy = False
        self.outcome = 0
        self.preparation_lines: list[str] = []
        self.preparation_error: str | None = None
        self.preparation_complete = False
        self.doctor_report: dict | None = None
        self.doctor_error: str | None = None
        self.progress_state = ProgressState()
        self.run_started_at: float | None = None
        self.run_optimizer = "-"
        self.run_status = "waiting"
        self.run_result: dict | None = None
        self.run_failure_reason: str | None = None
        self.run_timer = None

    def compose(self) -> ComposeResult:
        yield Static(id="path")
        yield Static(id="home-status", markup=False)
        with Horizontal(id="columns"):
            yield OptionList(id="options")
            with VerticalScroll(id="details-panel"):
                yield Static(id="details", markup=False)
        with VerticalScroll(id="review-panel"):
            yield Static(id="review", markup=False)
        with Vertical(id="run-panel"):
            yield Static(id="run-state")
            yield RichLog(id="event-log", max_lines=300, min_width=1, wrap=True,
                          highlight=False, markup=False, auto_scroll=False)
        yield ModelInput(id="entry")
        yield Static(id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#options", OptionList).border_title = _tr("선택지", "Options")
        self.query_one("#details-panel").border_title = _tr("상세", "Details")
        self._show("Home")

    def on_resize(self, event: Resize) -> None:
        self.set_class(event.size.width < 76, "narrow")

    def _show(self, page: str) -> None:
        self.page = page
        self.set_class(page in {"Review", "Result"}, "reviewing")
        options = self.query_one("#options", OptionList)
        options.border_title = {
            "Home": _tr("시작", "Start"),
            "Preparing": _tr("준비 단계", "Preparation"),
            "Doctor": _tr("사전 검사", "Pre-flight"),
            "Model": _tr("모델 설정", "Model Setup"),
        }.get(page, _tr("선택지", "Options"))
        entry = self.query_one("#entry", ModelInput)
        entry.endpoint_mode = page == "Model" and self.model_mode == "input" and self.model_field == "AGENT_OPT_MODEL_BASE_URL"
        entry.endpoint_rejected = False
        review = self.query_one("#review", Static)
        self.query_one("#path", Static).update(self._breadcrumb())
        self.query_one("#home-status", Static).styles.display = "block" if page == "Home" else "none"
        self.query_one("#home-status", Static).update(self.home_status)
        self.query_one("#run-panel").styles.display = "none"
        if page in {"Preparing", "Doctor"} and self.busy:
            hint = _tr("준비/진단이 진행 중입니다. 완료 후 계속 선택할 수 있습니다.",
                       "Preparation/checks are running. Choose an action when they finish.")
        elif page == "Preparing":
            hint = _tr("Enter 계속 · Esc Review로 돌아가기 · q 종료",
                       "Enter Continue · Esc Back to Review · q Quit")
        elif page == "Doctor":
            hint = _tr("↑↓ 검사 확인 · Enter 실행/재시도/뒤로 · Esc Review · q 종료",
                       "↑↓ Inspect checks · Enter Run/Retry/Back · Esc Review · q Quit")
        elif page == "Review":
            hint = _tr("↑↓ 탐색 · Enter 선택 · Esc 이전 · q 종료 · Tab 확인 내용 스크롤",
                       "↑↓ Navigate · Enter Select · Esc Back · q Quit · Tab scroll review")
        elif page == "Running":
            hint = _tr("Tab: 이벤트 로그 focus · ↑↓: 로그 스크롤 · Esc/q: 실행 종료 후 사용",
                       "Tab: focus event log · ↑↓: scroll log · Esc/q: after completion")
        else:
            hint = _tr("↑↓ 탐색 · Enter 선택 · Esc 이전 · q 종료 · Tab 입력/목록 전환",
                       "↑↓ Navigate · Enter Select · Esc Back · q Quit · Tab switch input/list")
        self.query_one("#hint", Static).update(hint)
        entry.password = False
        entry.value = ""
        entry.styles.display = "none"
        self.query_one("#review-panel").styles.display = "none"
        self.query_one("#columns").styles.display = "block"
        self.rows = []
        if page == "Home":
            self.rows = [ChoiceRow("new", "action", _tr("새 최적화", "New Optimization"),
                          _tr("Agent부터 차례대로 선택합니다.", "Select Agent, Harness, Optimizer, Dataset, then review."), True),
                         ChoiceRow("existing", "action", _tr("기존 실험", "Existing Experiment"),
                          _tr("experiment.toml을 선택하고 진단 후 실행합니다.", "Choose an experiment.toml, check it, then run."), True),
                         ChoiceRow("history", "action", _tr("이전 실행", "Run History"),
                          _tr("저장된 실행과 보고서 경로를 확인합니다.", "Inspect stored runs and report paths."), True),
                         ChoiceRow("advanced", "action", _tr("고급 설정", "Advanced Setup"),
                          _tr("맞춤 Agent·Harness·Optimizer·Dataset에는 agent-opt init을 사용합니다.",
                              "Use agent-opt init for custom Agent, Harness, Optimizer or Dataset."), True),
                         ChoiceRow("quit", "action", _tr("종료", "Quit"), _tr("앱을 종료합니다.", "Exit the app."), True)]
        elif page in STEPS:
            self.rows = preset_options(self.root, page, self.selections.get("Agent", "ace-rtl"), harness=self.selections.get('Harness'))
        elif page == "Existing":
            from agent_optimizer.setup_wizard import recent_configurations
            recent = recent_configurations(self.root)
            self.rows = [ChoiceRow(str(path), "configuration", str(path), _tr("최근 생성된 설정 · 선택하면 실행 전 확인으로 이동",
                                          "Recent generated configuration · review before running"), True)
                         for path in recent]
            self.rows.append(ChoiceRow("path.custom", "action", _tr("경로 직접 입력", "Enter a path"),
                              _tr("아래에 experiment.toml 경로를 입력하세요.",
                                  "Enter an experiment.toml path below."), True))
            entry.placeholder = _tr("기존 experiment.toml 경로", "Path to existing experiment.toml")
            entry.value = self.input_drafts.get("Existing", "")
            entry.styles.display = "block"
        elif page == "History":
            from agent_optimizer.app_paths import resolve_app_home, resolve_run_base
            from agent_optimizer.history import list_history
            bases = []
            if self.experiment is not None:
                try:
                    bases.append(resolve_run_base(load_experiment(self.experiment)))
                except (ConfigurationError, OSError, ValueError, KeyError, TypeError):
                    pass
            if self.run_result and self.run_result.get('run_dir'):
                bases.append(Path(self.run_result['run_dir']).parent)
            self.history = list_history(app_home=resolve_app_home(), project_root=self.root, run_bases=bases)
            self.rows = [ChoiceRow(row['run_id'], 'session' if row['kind'] == 'session' else 'report',
                         f"{row['run_id']} · {row['status']} · " + ('개별 결과 선택' if row['kind'] == 'session' else 'HTML 보고서 보기' if row['report_path'] else '진단/경로 보기'),
                         f"생성: {row['created_at']}\n상태: {row['status']}\n시도: {row['trials_used']}\n실제 경로: {row['run_dir']}\n보고서: {row['report_path']}\n" +
                         (row['diagnostic'] or 'Enter: HTML 보고서 보기 (열람 직전 재검증)') +
                         (f"\n재생성: agent-opt report {shlex.quote(row['run_dir'])} --html" if not row['report_path'] else ''), True)
                         for row in self.history]
        elif page == 'SessionHistory':
            self.rows = [ChoiceRow(row['run_id'], 'report', f"{row['run_id']} · {row['status']}",
                         f"실제 경로: {row['run_dir']}\n{row['diagnostic'] or 'Enter: HTML 보고서 보기'}") for row in self.session_history]
        elif page == 'Native':
            from agent_optimizer.locale import t
            fields = {'cids': 'CID(쉼표 구분): cid002/cid004/cid007/cid016',
                      'rows': 'row ID → split JSON: {"ROW_A":"train","ROW_B":"validation"}',
                      'dataset': '고정 원본 CVDP JSONL 절대경로(trusted)',
                      'source': '준비된 native source 절대경로(upstream과 배타)',
                      'upstream': '고정 로컬 upstream 절대경로(source와 배타)',
                      'python': 'native Python 3.12 경로(미입력: 현재 interpreter)',
                      'evaluator': '공식 evaluator repo/python/sim_image/sim_image_id JSON'}
            self.rows = [ChoiceRow(field, 'native.field', t(label),
                          f"{t(label)}\n{t('현재')}: {self.native_values.get(field, t('미설정'))}\n{t('CID007: PNR·상용 helper row는 선택 후 검증에서 명시 거부됩니다.')}") for field, label in fields.items()]
            self.rows.append(ChoiceRow('rows.pick', 'action', t('고정 데이터의 row 목록에서 선택'),
                             t('CID와 dataset 경로 입력 후 과제 ID·target·지원 상태를 확인하고 split을 직접 선택합니다.')))
            self.rows.append(ChoiceRow('native.continue', 'action', t('모델 설정으로 계속'), t('선택을 검증합니다. 준비·다운로드·모델 호출 없음.')))
            entry.placeholder = t(fields[self.native_field])
            value = self.native_values.get(self.native_field, '')
            entry.value = (','.join(value) if self.native_field == 'cids' else json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value))
            entry.styles.display = 'block'
        elif page == 'NativeRows':
            from agent_optimizer.locale import t
            selected = self.native_values.get('rows', {})
            self.rows = [ChoiceRow(row['id'], 'native.row',
                          f"{row['id']} · {row['cid']} · {selected.get(row['id'], t('미선택'))}",
                          f"target: {', '.join(row['targets'])}\n{t('도구')}: {', '.join(row['tools'])}\n" +
                          (row['reason'] or t('row 형태 검토만 완료; 실환경 not_run. Enter로 split을 명시하세요.')),
                         row['supported'], row['reason']) for row in self.native_rows_catalog]
            self.rows.append(ChoiceRow('native.back', 'action', t('Native 설정으로 돌아가기'), t('선택한 row·split을 보존합니다.')))
        elif page == 'NativeSplit':
            from agent_optimizer.locale import t
            self.rows = [ChoiceRow(split, 'native.split', split, t({
                'train': 'Optimizer 이력·변이 근거에 사용할 공개 과제',
                'validation': '수치 비교·후보 선택; private 평가 자료는 공개하지 않음',
                'test': '선택 고정 후 최종 평가에만 사용',
                'remove': '이 row 선택을 제거'}[split])) for split in ('train', 'validation', 'test', 'remove')]
        elif page == "Review":
            self.rows = [ChoiceRow("model.edit", "action", _tr("모델 설정 수정", "Edit Model Settings"),
                          _tr("현재 환경 값을 확인하거나 이번 세션에서 모델 값을 바꿉니다.",
                              "Review current model values or change them for this session."), True),
                         ChoiceRow("prepare", "action", _tr("준비하고 실행", "Prepare and Run"),
                          _tr("진단을 통과한 뒤에만 실행합니다.", "Run only after readiness checks pass."), True),
                         ChoiceRow("cancel", "action", _tr("취소", "Cancel"), _tr("자산 준비나 설정 파일을 만들지 않고 돌아갑니다.",
                                                 "Return without preparing assets or writing a configuration."), True)]
            self.query_one("#review-panel").styles.display = "block"
            review.update(self._review())
        elif page == "Preparing":
            if self.preparation_error:
                self.rows = [ChoiceRow("prepare.retry", "action", _tr("준비 다시 시도", "Retry preparation"),
                              _tr("준비 단계를 다시 실행합니다.", "Run the preparation steps again."), True),
                             ChoiceRow("review", "action", _tr("Review로 돌아가기", "Back to Review"),
                              _tr("설정이나 자산 선택을 변경합니다.", "Change the selection or review settings."), True)]
            elif self.preparation_complete:
                self.rows = [ChoiceRow("doctor", "action", _tr("Doctor로 계속", "Continue to Doctor"),
                              _tr("준비 결과를 확인하고 실행 전 검사를 시작합니다.",
                                  "Review preparation and start the pre-flight checks."), True),
                             ChoiceRow("review", "action", _tr("Review로 돌아가기", "Back to Review"),
                              _tr("설정이나 자산 선택을 변경합니다.", "Change the selection or review settings."), True)]
            else:
                self.rows = [ChoiceRow("preparing", "status", _tr("선택한 자산 준비 중", "Preparing selected assets"),
                              _tr("이 화면에 준비 상태를 표시합니다.", "Preparation progress is shown in the details panel."), True)]
        elif page == "Doctor":
            self.rows = self._doctor_rows()
        elif page == "Result":
            self.rows = [ChoiceRow("doctor", "action", _tr("진단으로 돌아가기", "Back to Doctor"),
                          _tr("실행 전 진단 결과와 선택을 확인합니다.",
                              "Return to the pre-flight result and selection."), True),
                         ChoiceRow("home", "action", _tr("시작 화면으로", "Back to Home"),
                          _tr("다른 실행을 시작하거나 이전 결과를 확인합니다.",
                              "Start another optimization or inspect run history."), True)]
            if self.run_result and self.run_result.get("report_html"):
                self.rows.append(ChoiceRow("report.open", "action", "HTML 보고서 보기",
                                           "저장된 HTML 보고서를 검증한 뒤 열람합니다."))
            self.query_one("#review-panel").styles.display = "block"
            review.update(self._result_text())
        elif page == "Advanced":
            self.rows = [ChoiceRow("existing", "action", _tr("기존 설정 선택", "Select existing config"),
                          _tr("agent-opt init으로 생성한 설정을 실행합니다.", "Run a configuration created by agent-opt init."), True)]
        elif page == "Workspace":
            entry.placeholder = _tr("ACE-RTL 작업공간 경로", "ACE-RTL workspace path")
            entry.value = self.input_drafts.get("Workspace", "" if self.workspace == self.root else str(self.workspace))
            entry.styles.display = "block"
            self.rows = [ChoiceRow("workspace.custom", "action", _tr("작업공간 선택", "Select workspace"),
                          _tr("고정 Git·CVDP·driver·Docker 자산은 실행 확인 뒤 준비합니다.",
                              "Pinned Git, CVDP, driver and Docker assets are prepared after review."), True)]
        elif page == "Model":
            if self.model_mode == "choices":
                self.rows = self._model_choice_rows(self.model_field)
            elif self.model_mode == "input":
                field = self.model_field
                current, _source = self._model_value(field)
                entry.placeholder = f"{self._model_label(field)} ({_tr('입력 후 Enter', 'type and press Enter')})"
                if field == "AGENT_OPT_MODEL_BASE_URL" and display_endpoint(current) != current:
                    current = ""
                if field == "AGENT_OPT_MODEL_BASE_URL" and endpoint_contains_credentials(self.input_drafts.get(field, "")):
                    self.input_drafts.pop(field, None)
                entry.password = self._is_secret_field(field)
                entry.value = self.input_drafts.get(field, "" if entry.password else current)
                entry.styles.display = "block"
                self.rows = [ChoiceRow(field, "model.input", self._model_label(field), _tr(
                    "이번 세션에서만 사용됩니다. 비밀 값은 입력 중 숨겨집니다.",
                    "Session-only value; secrets are masked while typing."), True)]
            else:
                self.rows = [self._model_field_row(field) for field in self.model_fields]
                if not self.model_fields:
                    self.rows = [ChoiceRow("review", "action", _tr("Review로 계속", "Continue to Review"),
                                  _tr("모델 설정 불필요 · 선택한 조합은 Model API를 사용하지 않습니다.",
                                      "No model settings required · this selection does not use a Model API."), True)]
                else:
                    self.rows.append(ChoiceRow("review", "action", _tr("Review로 계속", "Continue to Review"),
                                      _tr("선택한 값과 실행 조건을 확인합니다.",
                                          "Review the selected values and run requirements."), True))
        elif page == "Running":
            self.rows = []
            self.query_one("#run-panel").styles.display = "block"
            self.query_one("#columns").styles.display = "none"
            self.query_one("#run-state").border_title = _tr("최적화", "Optimization")
            self.query_one("#event-log", RichLog).border_title = _tr("이벤트", "Events")
            options.set_options([])
            self._refresh_run_state()
            self.query_one("#event-log", RichLog).focus()
            return
        options.set_options([Option(Text(row.label + ("  ×" if not row.enabled else ""),
                                        style=self._option_style(page, index, row)), id=row.id)
                             for index, row in enumerate(self.rows)])
        focus_key = self._focus_key()
        index = next((i for i, row in enumerate(self.rows) if row.id == self.focus_ids.get(focus_key)),
                     min(self.focus_indices.get(page, 0), len(self.rows) - 1))
        if index < 0:
            index = None
        options.highlighted = index
        self._detail(index)
        if page in {"Existing", "Workspace"} or page == "Model" and self.model_mode == "input":
            entry.focus()
        else:
            options.focus()

    def _focus_key(self) -> str:
        return (f"Model:{self.model_mode}:{self.model_field if self.model_mode != 'fields' else ''}"
                if self.page == "Model" else self.page)

    def _breadcrumb(self) -> str:
        if self.page == "Home":
            return "Agent Optimizer\n" + _tr("실행할 작업을 선택하세요", "Choose what to do next")
        if self.page in STEPS:
            selected = " / ".join(self.selections[step] for step in STEPS
                                  if step in self.selections and step != self.page)
            current = f"{_tr('새 최적화', 'New Optimization')}  ›  {_name(self.page)}"
            return "Agent Optimizer\n" + current + (f"\n{selected}" if selected else "")
        return f"Agent Optimizer\n{_name(self.page)}"

    def _is_secret_field(self, field: str) -> bool:
        name = field.upper()
        return any(marker in name for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD"))

    def _model_label(self, field: str) -> str:
        labels = {
            "AGENT_OPT_MODEL": _tr("Agent 모델", "Agent model"),
            "AGENT_OPT_MODEL_BASE_URL": _tr("API 주소", "API Endpoint"),
            "AGENT_OPT_MODEL_ID": _tr("API 모델 ID", "API model ID"),
            "AGENT_OPT_MODEL_API_KEY": _tr("API key", "API key"),
            "OPENROUTER_API_KEY": _tr("OpenRouter API key", "OpenRouter API key"),
        }
        return labels.get(field, f"{_tr('모델 선택자', 'Model selector')} · {field}")

    @property
    def model_presets(self) -> dict[str, dict[str, str]]:
        return {name: dict(values) for name, values in self._model_presets.items()}

    @model_presets.setter
    def model_presets(self, presets: dict[str, dict[str, str]]) -> None:
        # F supplies explicitly selected non-secret configuration; no dotenv/Home scan.
        clean = {}
        for name, values in presets.items():
            allowed = {}
            for field in ("AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID"):
                value = values.get(field)
                if not isinstance(value, str) or not value or any(c.isspace() for c in value):
                    continue
                if field == "AGENT_OPT_MODEL_BASE_URL" and display_endpoint(value) != value:
                    continue
                allowed[field] = value
            if allowed:
                clean[name] = allowed
        self._model_presets = clean

    def _model_usage(self) -> str:
        metadata = self.component_metadata.get(self.selections.get("Harness", ""), {})
        if self.experiment:
            spec = load_experiment(self.experiment)
            optimizer_api = any(stage["optimizer"] in {"gepa", "meta_harness", "ecdysis"}
                                for stage in spec.get("stages", []))
        else:
            optimizer_api = self.selections.get("Optimizer") in {"gepa", "meta_harness", "ecdysis"}
        roles = ", ".join(metadata.get("model_roles", []))
        agent = f"Agent API: {roles}" if roles else "Agent 설정: 선택한 Harness의 모델 selector"
        optimizer = "Optimizer API: 필수 · 후보 생성/반성 호출" if optimizer_api else "Optimizer API: 불필요 · 모델 호출 없음"
        return f"{agent}\n{optimizer}\nAgent/Optimizer 사용량은 별도로 기록합니다."

    def model_configuration(self) -> dict:
        """Serializable UI metadata only; execution credentials are never returned here."""
        return {"fields": {field: {"value": None if self._is_secret_field(field) else
                                   self._shown_model_value(field, self._model_value(field)[0]),
                                   "configured": bool(self._model_value(field)[0]),
                                   "source": self._model_value(field)[1]}
                           for field in self._required_model_fields()}, "usage": self._model_usage()}

    def _model_value(self, field: str) -> tuple[str, str]:
        selectors = self._model_selector_fields()
        if self.model_values.get(field):
            value, source = self.model_values[field], self.model_sources.get(field, "session")
        else:
            from agent_optimizer.model_input import environment_snapshot
            value, source = environment_snapshot().get(field, ""), "environment"
        if value:
            if field in selectors and "/" not in value:
                value = "compatible/" + value
            return value, source
        if field == "AGENT_OPT_MODEL_ID":
            models = set()
            for selector_field in selectors:
                from agent_optimizer.model_input import environment_snapshot
                selector = self.model_values.get(selector_field) or environment_snapshot().get(selector_field, "")
                if selector.startswith("compatible/") and selector.removeprefix("compatible/"):
                    models.add(selector.removeprefix("compatible/"))
                elif selector and "/" not in selector:
                    models.add(selector)
            if len(models) == 1:
                return next(iter(models)), "derived"
            if models:
                return "", "missing"  # Conflicting profiles cannot supply one implicit API model.
            return DEFAULT_MODEL_ID, "default"
        return "", "missing"

    def _source_label(self, source: str) -> str:
        return {
            "environment": _tr("환경", "env"),
            "default": _tr("기본값", "default"),
            "session": _tr("세션", "session"),
            "file": _tr("파일", "file"),
            "derived": _tr("Agent 선택자에서 유도", "derived from Agent selector"),
            "missing": _tr("미설정", "not set"),
        }[source]

    def _shown_model_value(self, field: str, value: str) -> str:
        if self._is_secret_field(field):
            return _tr("설정됨", "configured") if value else _tr("미설정", "not configured")
        if field == "AGENT_OPT_MODEL_BASE_URL" and value:
            return display_endpoint(value)
        return value or _tr("설정 필요", "not configured")

    def _model_field_row(self, field: str) -> ChoiceRow:
        value, source = self._model_value(field)
        shown = self._shown_model_value(field, value)
        description = f"{_tr('출처', 'source')}: {self._source_label(source)}"
        role = "Agent 호출 모델 선택자" if field not in {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID",
                                                       "AGENT_OPT_MODEL_API_KEY"} else "Optimizer API · Agent compatible API 공통 연결"
        group = "API 연결" if field in {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY"} else "Agent 설정"
        return ChoiceRow(field, "model.field", f"{group} · {self._model_label(field)}  {shown} [{self._source_label(source)}]",
                         f"{self._model_usage()}\n\n{role}\n필수 입력\n{description}")

    def _model_choice_rows(self, field: str) -> list[ChoiceRow]:
        rows = []
        from agent_optimizer.model_input import environment_snapshot
        environment_value = environment_snapshot().get(field, "")
        if environment_value:
            shown = self._shown_model_value(field, environment_value)
            rows.append(ChoiceRow("environment", "model.choice", _tr("현재 환경", "Current environment") + f" · {shown}",
                         _tr("기존 환경 값을 사용합니다.", "Use the existing environment value."), True))
        session_value = self.model_values.get(field, "")
        if session_value:
            shown = self._shown_model_value(field, session_value)
            rows.append(ChoiceRow("session", "model.choice", _tr("현재 세션", "Current session") + f" · {shown}",
                         _tr("현재 앱 세션의 값을 유지합니다.", "Keep the current app-session value."), True))
        if field == "AGENT_OPT_MODEL_ID":
            rows.append(ChoiceRow("default", "model.choice", _tr("앱 기본값", "Application default") + f" · {DEFAULT_MODEL_ID}",
                         _tr("models.py의 공통 기본 모델 ID입니다.",
                             "Shared application default model ID."), True))
        if field in {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID"}:
            for name, preset in self.model_presets.items():
                value = preset.get(field)
                if value:
                    rows.append(ChoiceRow(f"preset:{name}", "model.choice", f"{name} · {self._shown_model_value(field, value)}",
                                          "명시적으로 제공된 비밀 없는 named preset · 출처: 파일"))
        rows.append(ChoiceRow("custom", "model.choice", _tr("직접 입력…", "Custom…"),
                     _tr("값은 이번 앱 세션에서만 사용합니다.",
                         "Use this value for this app session only."), True))
        return rows

    def _doctor_rows(self) -> list[ChoiceRow]:
        if self.doctor_error:
            rows = [ChoiceRow("doctor.retry", "action", _tr("진단 다시 시도", "Retry checks"),
                     _tr("사전 검사를 다시 실행합니다.", "Run the pre-flight checks again."), True),
                    ChoiceRow("review", "action", _tr("Review로 돌아가기", "Back to Review"),
                     _tr("설정이나 모델 값을 수정합니다.", "Edit the experiment or model settings."), True)]
            return rows
        if self.doctor_report is None:
            return [ChoiceRow("checking", "status", _tr("검사 진행 중", "Checks in progress"),
                     _tr("선택한 experiment의 준비 상태를 확인합니다.",
                         "Checking readiness for the selected experiment."), True)]
        rows = []
        symbols = {"ok": "✓", "error": "✗", "blocked": "○"}
        for check in self.doctor_report.get("checks", []):
            rows.append(ChoiceRow(check["id"], "check", f"{symbols.get(check['status'], '?')} {check['id']}",
                         check["message"], True, check["status"]))
        if self.doctor_report.get("ready"):
            rows.append(ChoiceRow("run", "action", _tr("최적화 실행", "Run Optimization"),
                         _tr("사전 검사를 통과했습니다. 실행을 시작합니다.",
                             "Pre-flight checks passed. Start the optimization."), True))
        rows.append(ChoiceRow("doctor.retry", "action", _tr("진단 다시 시도", "Retry checks"),
                     _tr("실행 없이 사전 검사를 다시 수행합니다.",
                         "Repeat pre-flight checks without running the optimizer."), True))
        rows.append(ChoiceRow("review", "action", _tr("Review로 돌아가기", "Back to Review"),
                     _tr("모델 설정이나 실행 선택을 수정합니다.",
                         "Edit model settings or the experiment selection."), True))
        return rows

    def _option_style(self, page: str, index: int, row: ChoiceRow) -> str:
        if not row[2]:
            return "dim"
        if page == "Doctor" and self.doctor_report is not None and \
                index < len(self.doctor_report.get("checks", [])):
            return {"ok": "green", "error": "red", "blocked": "yellow"}.get(row[3], "")
        return ""

    def _detail(self, index: int | None) -> None:
        # Highlight messages already queued during teardown may outlive their widgets.
        if not self.query('#details-panel').nodes or not self.query('#details').nodes:
            return
        if self.page == "Preparing":
            self.query_one("#details", Static).update(self._preparation_view())
            return
        if self.page == "Doctor":
            self.query_one("#details", Static).update(self._doctor_detail(index))
            return
        if index is None or not 0 <= index < len(self.rows):
            diagnostics = getattr(self.history, 'diagnostics', []) if self.page == 'History' else []
            self.query_one("#details", Static).update(_tr("표시할 항목이 없습니다.", "No items to show.") + '\n' + '\n'.join(diagnostics))
            return
        row = self.rows[index]
        self.query_one("#details-panel").scroll_home(animate=False)
        status = row[3] if len(row) > 3 else _tr("사용 가능", "Available") if row[2] else _tr("선택 불가", "Unavailable")
        next_step = (STEPS[STEPS.index(self.page) + 1] if self.page in STEPS[:-1] else
                     "Review" if self.page == "Dataset" else "")
        if not row[2]:
            if self.page == "Agent":
                alternatives = [_tr("기존 실험", "Existing Experiment"),
                                _tr("고급 설정", "Advanced Setup")]
            else:
                alternatives = [choice[0] for choice in self.rows
                                if choice[2] and choice[0] != row[0]][:2]
                alternatives.extend([_tr("기존 실험", "Existing Experiment"),
                                     _tr("고급 설정", "Advanced Setup")])
            detail = (f"{row[0]}\n\n{_tr('선택할 수 없는 이유', 'Why unavailable')}\n  {row[1]}\n\n"
                      f"{_tr('대신 시도', 'Try instead')}\n" +
                      "\n".join(f"  • {value}" for value in dict.fromkeys(alternatives)))
        else:
            detail = f"{row[0]}\n\n{row[1]}"
            if status not in {"구현됨", "사용 가능", "Implemented", "Available"}:
                detail += f"\n\n{_tr('준비 정보', 'Preparation')}\n  {status}"
        if next_step:
            detail += f"\n\n{_tr('다음', 'Next')}\n  {_name(next_step)}"
        if self.page in STEPS:
            metadata = self.component_metadata.get(row.id, {})
            surface = metadata.get("edit_surface") or (self._edit_surface(row.id) if self.page == "Optimizer"
                                                       else _tr("변경 없음", "No changes"))
            description = metadata.get("description", row.description)
            if self.page == "Optimizer":
                description = description.replace(ACE_SCAFFOLD, surface).replace("role-guidance.md", surface)
            combination = " / ".join(f"{step}: {value}" for step, value in self.selections.items()) or "미선택"
            detail = (f"{row.label}\n\n{_tr('무엇인가', 'What it is')}\n{description}"
                      f"\n\n{_tr('무엇을 바꾸나', 'What it changes')}\n{surface}"
                      f"\n\n{_tr('현재 조합', 'Current combination')}\n{combination}"
                      f"\n\n{_tr('필요한 준비', 'Preparation')}\n{row.reason or _tr('사용 가능', 'Available')}"
                      f"\n\n{_tr('제한·다음 행동', 'Limits / next action')}\n" +
                      (f"{_tr('선택할 수 없는 이유', 'Why unavailable')}: {row.reason}\n"
                       + _tr("대신 시도: 기존 실험 / 고급 설정", "Try instead: Existing Experiment / Advanced Setup")
                       if not row.enabled else f"{_tr('다음', 'Next')}: {_name(next_step) if next_step else row.id}"))
        if self.page == "Advanced":
            detail += "\n\nagent-opt init\nagent-opt init --help"
        self.query_one("#details", Static).update(detail)

    def on_preparation_line(self, message: PreparationLine) -> None:
        self._preparation_line(message.line)

    def _preparation_line(self, line: str) -> None:
        safe = self._redact_secrets(line.strip())
        if not safe:
            return
        lowered = safe.casefold()
        mark = "✗" if "failed" in lowered or "실패" in safe else \
            "✓" if "complete" in lowered or "완료" in safe else "●"
        self.preparation_lines.append(f"{mark} {safe}")
        self.preparation_lines = self.preparation_lines[-100:]
        if self.page == "Preparing":
            self.query_one("#details", Static).update(self._preparation_view())

    def _preparation_view(self) -> str:
        heading = f"{_tr('준비 중', 'Preparing')}\n────────"
        lines = [heading, *self.preparation_lines]
        if self.preparation_error:
            lines += ["", _tr("준비 실패", "Preparation failed"),
                      self._redact_secrets(self.preparation_error), "",
                      _tr("다음: 준비를 다시 시도하거나 Review로 돌아가세요.",
                          "Next: retry preparation or return to Review.")]
        elif not self.preparation_lines:
            lines.append(_tr("준비 단계가 시작되기를 기다리는 중…",
                             "Waiting for preparation steps…"))
        return "\n".join(lines)

    def _doctor_detail(self, index: int | None) -> str:
        if self.doctor_error:
            guidance = _tr('다음: 다시 시도하거나 Review로 돌아가세요.',
                           'Next: retry checks or return to Review.')
            return (f"{_tr('사전 진단 실패', 'Pre-flight checks failed')}\n\n"
                    f"{self._redact_secrets(self.doctor_error)}\n\n"
                    f"{guidance}")
        if self.doctor_report is None:
            return (f"{_tr('사전 검사 진행 중', 'Pre-flight checks in progress')}\n\n"
                    + _tr("실행 준비 상태를 확인하고 있습니다.",
                          "Checking whether the experiment is ready to run."))
        checks = self.doctor_report.get("checks", [])
        counts = {status: sum(row["status"] == status for row in checks)
                  for status in ("ok", "error", "blocked")}
        summary = (f"{counts['ok']} / {len(checks)} " + _tr("검사 통과", "checks passed")
                   if self.doctor_report.get("ready") else
                   f"{counts['ok']} / {len(checks)} " + _tr("검사 통과", "checks passed") +
                   f" · {counts['error']} " + _tr("실패", "failed") +
                   f" · {counts['blocked']} " + _tr("차단", "blocked"))
        if index is None or index >= len(checks):
            action = self.rows[index][0] if index is not None and index < len(self.rows) else _name("Doctor")
            detail = f"{action}\n\n{summary}"
        else:
            check = checks[index]
            symbol = {"ok": "✓", "error": "✗", "blocked": "○"}.get(check["status"], "?")
            status = {"ok": _tr("준비됨", "Ready"), "error": _tr("실패", "Failed"),
                      "blocked": _tr("차단됨", "Blocked")}.get(check["status"], check["status"])
            rendered = render_diagnostic(check)
            detail = (f"{symbol} {check['id']} · {check['area']} · {status}\n\n"
                      f"{self._redact_secrets(rendered)}")
            if check["id"] == "model.probe" and check["status"] == "ok":
                detail += "\n\n" + _tr(
                    "Model connectivity: OK는 연결 probe 성공이며 Agent 최적화 전체 성공을 보장하지 않습니다.",
                    "Model connectivity: OK confirms the probe only; it does not guarantee the full Agent optimization.")
            detail += f"\n\n{summary}"
        return self._redact_secrets(detail)

    def _redact_secrets(self, text: object) -> str:
        rendered = str(text)
        from agent_optimizer.model_input import environment_snapshot
        sources = [*environment_snapshot().items(), *self.model_values.items()]
        secrets = {value for name, value in sources if value and self._is_secret_field(name)}
        for name, value in sources:
            if not value or name not in {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ENDPOINT"}:
                continue
            try:
                endpoint = urlsplit(value)
            except ValueError:
                continue
            for component in (endpoint.username, endpoint.password):
                if component:
                    secrets.update((component, unquote(component)))
            for query in (endpoint.query, endpoint.fragment):
                if query:
                    secrets.add(query)
                for raw_parameter in query.replace(";", "&").split("&"):
                    parameter, separator, raw_credential = raw_parameter.partition("=")
                    if separator and raw_credential:
                        secrets.update((raw_credential, unquote_plus(raw_credential)))
                    elif parameter:
                        secrets.add(parameter)
        for secret in sorted(secrets, key=len, reverse=True):
            rendered = rendered.replace(secret, "••••")
        return rendered

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.focus_indices[self.page] = event.option_index
        if 0 <= event.option_index < len(self.rows):
            self.focus_ids[self._focus_key()] = self.rows[event.option_index].id
        self._detail(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index >= len(self.rows):
            return
        if not self.rows[event.option_index][2]:
            self.notify(_tr("선택 불가 이유와 대안을 상세 영역에서 확인하세요.",
                            "Review the reason and alternatives in the details panel."))
            return
        index = event.option_index
        row = self.rows[index]
        action = row.id
        if self.page == "Home":
            if action == "new":
                self.experiment = None
                self.workspace = self.root
                self.selections.clear()
                self.focus_indices.clear()
                self.focus_ids.clear()
                self._show("Agent")
            elif action == "existing":
                self._show("Existing")
            elif action == "history":
                self._show("History")
            elif action == "advanced":
                self._show("Advanced")
            else:
                self.exit(0)
        elif self.page in STEPS:
            if row.kind == "action":
                self._show({"advanced": "Advanced", "existing": "Existing"}[action])
                return
            value = row.id
            if self.selections.get(self.page) != value:
                self.experiment = None
                self.preparation_complete = False
                self.doctor_report = None
                for step in STEPS[STEPS.index(self.page) + 1:]:
                    self.selections.pop(step, None)
                    self.focus_indices.pop(step, None)
                    self.focus_ids.pop(step, None)
            self.selections[self.page] = value
            next_page = "Model" if self.page == "Dataset" else STEPS[STEPS.index(self.page) + 1]
            self.return_page = "Dataset"
            if next_page == 'Model' and self.selections.get('Harness') == 'ace-native':
                next_page = 'Native'
            elif next_page == "Model" and value == "cvdp" and not is_source_checkout(self.root):
                next_page = "Workspace"
                self.workspace_back = "Dataset"
            if next_page == "Model":
                self._open_model_setup("Dataset")
            else:
                self._show(next_page)
        elif self.page == "Existing":
            if action == "path.custom":
                self.query_one(Input).focus()
            else:
                self._load_existing(Path(row.id))
        elif self.page == "History":
            history = next(item for item in self.history if item['run_id'] == row.id)
            if history['kind'] == 'session':
                from agent_optimizer.history import list_history
                from agent_optimizer.app_paths import resolve_app_home
                rows = list_history(app_home=resolve_app_home(), run_bases=(Path(history['run_dir']).parent,), limit=10000)
                self.session_history = [item for item in rows if item['run_dir'] in history['child_runs']]
                self._show('SessionHistory')
            elif history['report_path']:
                self.action_open_report(Path(history['report_path']), history['status'], row=history)
            else:
                self._detail(index)
        elif self.page == 'SessionHistory':
            history = next(item for item in self.session_history if item['run_id'] == row.id)
            if history['report_path']:
                self.action_open_report(Path(history['report_path']), history['status'], row=history)
        elif self.page == 'Native':
            if action == 'rows.pick':
                try:
                    from agent_optimizer.native_selection import available_rows
                    if not self.native_values.get('dataset'):
                        raise ConfigurationError('고정 dataset 경로를 먼저 입력하세요')
                    self.native_rows_catalog = available_rows(self.workspace, self.native_values['dataset'], self.native_values.get('cids', []))
                    self._show('NativeRows')
                except (ConfigurationError, OSError, ValueError) as exc:
                    self._error(exc)
            elif action == 'native.continue':
                try:
                    from agent_optimizer.native_selection import validate_selection, inspect_selection
                    validate_selection(self.native_values.get('cids', []), self.native_values.get('rows', {}), self.selections['Optimizer'], root=self.workspace)
                    if not self.native_values.get('dataset') or bool(self.native_values.get('source')) == bool(self.native_values.get('upstream')):
                        raise ConfigurationError('고정 dataset와 source/upstream 중 하나를 명시하세요')
                    self.native_rows = inspect_selection(self.workspace, self.native_values['cids'], self.native_values['rows'], self.native_values['dataset'])
                    self._open_model_setup('Native')
                except (ConfigurationError, OSError, ValueError, TypeError) as exc:
                    self._error(exc)
            else:
                self.native_field = action
                self._show('Native')
                self.query_one(Input).focus()
        elif self.page == 'NativeRows':
            if action == 'native.back':
                self._show('Native')
            else:
                self.native_row_id = action
                self._show('NativeSplit')
        elif self.page == 'NativeSplit':
            chosen = self.native_values.setdefault('rows', {})
            previous = dict(chosen)
            if action == 'remove':
                chosen.pop(self.native_row_id, None)
            else:
                chosen[self.native_row_id] = action
            if chosen != previous:
                self._invalidate_native_configuration()
            self._show('NativeRows')
        elif self.page == "Review":
            if action == "model.edit":
                self._open_model_setup("Review")
            elif action == "prepare":
                self._start()
            else:
                self._show(self.return_page)
        elif self.page == "Preparing":
            if action == "prepare.retry":
                self._prepare()
            elif action == "doctor":
                self._check_doctor()
            elif action == "review":
                self._show("Review")
        elif self.page == "Doctor":
            if row.kind == "check":
                self._detail(index)
                return
            if action == "run":
                self._run()
            elif action == "doctor.retry":
                self._check_doctor()
            elif action == "review":
                self._show("Review")
        elif self.page == "Result":
            if action == "report.open":
                self.action_open_report(Path(self.run_result["report_html"]),
                                        self.run_result.get("status", "completed"))
            else:
                self._show("Doctor" if action == "doctor" else "Home")
        elif self.page == "Advanced":
            self._show("Existing")
        elif self.page == "Workspace":
            self.query_one(Input).focus()
        elif self.page == "Model":
            self._select_model_option(index)

    def _open_model_setup(self, return_page: str) -> None:
        try:
            self.model_fields = self._required_model_fields()
        except (ConfigurationError, OSError) as exc:
            self._error(exc)
            return
        self.model_return_page = return_page
        self.model_mode = "fields"
        self.model_field = ""
        self.model_index = 0
        self._show("Model")

    def _select_model_option(self, index: int) -> None:
        row = self.rows[index]
        if self.model_mode == "fields":
            if row.kind == "model.field":
                self.model_field = row.id
                self.model_index = self.model_fields.index(row.id)
                if self._is_secret_field(self.model_field) and not self._model_value(self.model_field)[0]:
                    self.model_mode = "input"
                    self.focus_indices["Model"] = 0
                    self._show("Model")
                    return
                self.model_mode = "choices"
                self.focus_indices["Model"] = 0
                self._show("Model")
                return
            missing = self._missing_model_fields()
            if missing:
                self.model_index = self.model_fields.index(missing[0])
                self.focus_indices["Model"] = self.model_index
                self._show("Model")
                self.notify(_tr("필수 모델 값을 설정한 뒤 계속하세요.",
                                "Set the required model values before continuing."))
                return
            try:
                self._validate_model_selection()
            except ConfigurationError as exc:
                self._error(exc)
                return
            if self.model_return_page in {"Dataset", "Workspace", 'Native'}:
                self.return_page = "Model"
            self._show("Review")
            return
        if self.model_mode == "choices":
            action = row.id
            field = self.model_field
            if action == "custom":
                self.model_mode = "input"
                self._show("Model")
                return
            if action == "environment":
                self.model_values.pop(field, None)
                self.model_sources.pop(field, None)
            elif action == "default":
                self.model_values[field] = DEFAULT_MODEL_ID
                self.model_sources[field] = "default"
            elif action.startswith("preset:"):
                self.model_values[field] = self.model_presets[action.removeprefix("preset:")][field]
                self.model_sources[field] = "file"
            self.model_mode = "fields"
            self.model_fields = self._required_model_fields()
            self.model_index = self.model_fields.index(field)
            self.focus_indices["Model"] = self.model_index
            self._show("Model")

    def on_input_changed(self, event: Input.Changed) -> None:
        # Endpoints remain plaintext; credentials are rejected rather than made executable.
        if event.input.has_focus and self.page in {"Existing", "Workspace", "Model"}:
            key = self.model_field if self.page == "Model" else self.page
            self._remember_input_draft(key, event.value)

    def _remember_input_draft(self, field: str, value: str) -> None:
        if field == "AGENT_OPT_MODEL_BASE_URL" and endpoint_contains_credentials(value):
            self.input_drafts.pop(field, None)
        else:
            self.input_drafts[field] = value

    def on_model_input_endpoint_rejected(self, event: ModelInput.EndpointRejected) -> None:
        self.input_drafts.pop("AGENT_OPT_MODEL_BASE_URL", None)
        if self.page == "Model" and self.model_mode == "input":
            self._error(ConfigurationError(
                "자격증명 포함 URL은 입력할 수 없어 삭제했습니다. API key는 별도 입력하세요. "
                "정상 URL을 붙여넣거나 Esc 후 직접 입력을 다시 선택하세요."))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if self.page == 'Native':
            try:
                field = self.native_field
                parsed = [v.strip() for v in value.split(',') if v.strip()] if field == 'cids' else json.loads(value) if field in {'rows', 'evaluator'} and value else value
                from agent_optimizer.native_selection import validate_field
                validate_field(self.workspace, field, parsed)
                if self.native_values.get(field) != parsed:
                    self.native_values[field] = parsed
                    self._invalidate_native_configuration()
                self._show('Native')
            except (ValueError, ConfigurationError):
                self._error(ConfigurationError('native 선택 형식이 잘못됐습니다. 경로·CID·row JSON을 확인하세요.'))
        elif self.page == "Existing":
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
            self._open_model_setup("Workspace")
        elif self.page == "Model":
            if self.model_mode != "input":
                return
            field = self.model_field
            if not value:
                self.notify(_tr("값을 입력하세요.", "Enter a value."))
                return
            try:
                if field == "AGENT_OPT_MODEL_BASE_URL":
                    validate_endpoint(value)
                elif any(c.isspace() for c in value):
                    raise ConfigurationError("모델 ID·선택자·API key에 공백을 포함할 수 없습니다")
            except ConfigurationError as exc:
                self._error(exc)
                if field == "AGENT_OPT_MODEL_BASE_URL" and display_endpoint(value) != value:
                    self.input_drafts.pop(field, None)
                    event.input.value = ""
                return
            self.model_values[field] = value
            self.input_drafts.pop(field, None)
            self.model_sources[field] = "session"
            self.model_mode = "fields"
            self.model_fields = self._required_model_fields()
            self.model_index = self.model_fields.index(field)
            self.focus_indices["Model"] = self.model_index
            self._show("Model")

    def _load_existing(self, path: Path) -> None:
        try:
            spec = load_experiment(path.resolve())
        except (ConfigurationError, OSError, ValueError, KeyError, TypeError) as exc:
            self._error(exc)
            return
        self.experiment = spec["_source"]
        self.return_page = "Existing"
        self._show("Review")

    def _invalidate_native_configuration(self) -> None:
        self.experiment = None
        self.preparation_complete = False
        self.preparation_error = None
        self.doctor_report = None
        self.doctor_error = None
        self.native_rows = []

    def _selection_name(self, step: str, value: str) -> str:
        names = {
            "Agent": {"ace-rtl": "ACE-RTL", "rtl-solo": "rtl-solo", "rtl-team": "rtl-team"},
            "Harness": {"ace-opencode": "OpenCode", "fixture": "Fixture"},
            "Optimizer": {"meta_harness": "Meta-Harness", "file_variants": "FileVariants"},
            "Dataset": {"cvdp": "CVDP"},
        }
        return names.get(step, {}).get(value, value)

    def _edit_surface(self, optimizer: str) -> str:
        metadata = self.component_metadata.get(self.selections.get("Harness", ""), {})
        return metadata.get("edit_surfaces", {}).get(optimizer) or {
            "gepa": ACE_GUIDANCE, "meta_harness": ACE_SCAFFOLD,
            "file_variants": "configs/strategy.json"}.get(optimizer, _tr("변경 없음", "No changes"))

    def _model_summary(self) -> list[str]:
        fields = self._required_model_fields()
        lines = [_tr("모델", "Model"), "────────", self._model_usage()]
        if not fields:
            lines.append("  " + _tr("필요하지 않음", "Not required"))
            return lines
        section = None
        for field in fields:
            role = ("Optimizer API / Agent compatible API" if field in {
                "AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY"} else
                "Agent 설정")
            if role != section:
                lines += ["", f"  {role}", "  ────────"]
                section = role
            value, source = self._model_value(field)
            shown = self._shown_model_value(field, value)
            lines.append(f"  {self._model_label(field)}  {shown} [{self._source_label(source)}]")
        return lines

    def _review(self) -> str:
        if self.experiment is not None:
            try:
                spec = load_experiment(self.experiment)
                budget = spec["budget"]
                agent = ", ".join(a.id for a in spec["_agents"])
                harness = ", ".join(p["id"] for p in spec["_profiles"])
                optimizer = ", ".join(s["optimizer"] for s in spec.get("stages", [])) or "baseline"
                dataset = spec.get("benchmark")
                editable = ", ".join(
                    str(stage.get("config", {}).get("file")) for stage in spec.get('stages', [])
                    if stage.get("config", {}).get("file")) or _tr("변경 없음", "No changes")
                from agent_optimizer.app_paths import resolve_run_base
                report = str(resolve_run_base(spec) / '<run-id>/report.html')
            except (ConfigurationError, OSError, KeyError, TypeError) as exc:
                return self._redact_secrets(str(exc))
            selection = [f"  Agent       {agent}", f"  Harness     {harness}",
                          f"  Optimizer   {optimizer}", f"  Dataset     {dataset}"]
            counts = {split: sum(task.split == split for task in spec['_tasks']) for split in ('train', 'validation', 'test')}
            selection.append(f"  평가 방식  train {counts['train']} / validation {counts['validation']} / test {counts['test']} · final_test={str(spec.get('final_test', False)).lower()}")
            preparation = ["  " + _tr("기존 experiment 선택 · 자산 자동 준비 안 함",
                                       "Existing experiment · no automatic asset preparation")]
            external = ["  " + self._external_call_summary()]
        else:
            ace = self.selections.get("Agent") == "ace-rtl"
            optimizer = self.selections.get("Optimizer", "gepa")
            maximum = (1 if optimizer == "baseline" else 9) if ace else (4 if optimizer == "file_variants" else 3)
            timeout = 600 if ace else 120
            budget = {"max_trials": maximum, "trial_timeout_seconds": timeout,
                      "max_wall_time_seconds": (maximum * timeout + 360 if ace else 3600)}
            editable = self._edit_surface(optimizer)
            selection = [f"  {step:<11} {self._selection_name(step, self.selections.get(step, '-'))}"
                         for step in STEPS]
            preparation = ["  " + (_tr("고정 Git·CVDP·driver·Docker 자산을 준비/재사용",
                                        "Prepare or reuse pinned Git, CVDP, driver and Docker assets")
                                   if ace else _tr("로컬 합성 dataset fixture 준비",
                                                   "Prepare local synthetic dataset fixture")),
                           f"  {_tr('작업공간', 'Workspace')}  {'.' if self.workspace == self.root else self.workspace}"]
            external = ["  " + self._external_call_summary()]
            dataset = (_tr("cvdp · train 1 / validation 1 · final_test=false",
                           "cvdp · train 1 / validation 1 · final_test=false") if ace else
                       _tr("sample_eval · 합성 train / validation / test",
                           "sample_eval · synthetic train / validation / test"))
            from agent_optimizer.app_paths import app_path
            report = str(app_path('runs') / '<run-id>/report.html')
            if self.selections.get('Harness') == 'ace-native':
                selected = self.native_values.get('rows', {})
                counts = {split: sum(value == split for value in selected.values()) for split in ('train', 'validation', 'test')}
                dataset = f"cvdp · train {counts['train']} / validation {counts['validation']} / test {counts['test']} · final_test={str(counts['test'] > 0).lower()}"
            selection.append(f"  {_tr('평가 방식', 'Evaluation')}  {dataset}")
            if self.selections.get('Harness') == 'ace-native':
                from agent_optimizer.native_selection import native_trial_budget
                budget = {'max_trials': native_trial_budget(optimizer, self.native_values.get('rows', {}), root=self.workspace),
                          'trial_timeout_seconds': 600, 'max_wall_time_seconds': 3600}
                selection += [f"  CID         {', '.join(self.native_values.get('cids', []))}",
                              f"  rows        {len(self.native_values.get('rows', {}))} · {self.native_values.get('rows', {})}"]
                selection.extend(f"  target      {row['id']}: {', '.join(row['targets'])}" for row in getattr(self, 'native_rows', []))
                selection.extend(f"  {field:<11} {self.native_values.get(field, '현재 interpreter' if field == 'python' else '미설정')}"
                                 for field in ('source', 'upstream', 'dataset', 'python', 'evaluator'))
                preparation = ['  명시 로컬 고정 native 소스 export·CVDP hash/row 지원 검증; 설치/다운로드 없음',
                               '  평가 자산 미준비 시 doctor에서 차단; 별도 준비 필요']
                from agent_optimizer.app_paths import app_path
                selection.append(f"  설정 저장   {app_path('experiments')}/native-<id>/experiment.toml")

        rows = [f"{_tr('선택', 'Selection')}", "────────"]
        rows.extend(selection)
        rows += ["", *self._model_summary(), "", f"{_tr('최적화', 'Optimization')}", "────────",
                 f"  {_tr('수정 대상', 'Edit target')}  {editable}",
                 "", f"{_tr('예산', 'Budget')}", "────────",
                 f"  {_tr('최대 trial budget', 'Trial budget maximum')}  {budget['max_trials']}",
                 f"  {_tr('trial timeout', 'Trial timeout')}  {budget['trial_timeout_seconds']}s",
                 f"  {_tr('wall time', 'Wall time')}  {budget['max_wall_time_seconds']}s",
                 "", f"{_tr('준비', 'Preparation')}", "────────", *preparation,
                 "", f"{_tr('외부 호출', 'External calls')}", "────────", *external,
                 "", f"{_tr('출력', 'Output')}", "────────",
                 f"  {_tr('보고서', 'Report')}: {report}"]
        if self.experiment is not None:
            rows.insert(2, f"  {_tr('설정', 'Configuration')}  {self.experiment}")
        rows += ["", _tr("Enter: 선택한 설정으로 계속   Esc: 이전 단계", "Enter: continue   Esc: back")]
        # All model values above are rendered by field type. Do not replace a one-letter
        # key throughout ordinary labels/URLs; diagnostics still use strict redaction.
        return "\n".join(rows)

    def _model_selector_fields(self, spec: dict | None = None) -> list[str]:
        """Use the selected profiles, including user-defined model_env names."""
        if self.experiment:
            spec = spec if spec is not None else load_experiment(self.experiment)
            return list(dict.fromkeys(p.get("model_env", "AGENT_OPT_MODEL") for p in spec["_profiles"]
                                      if p["adapter"] == "opencode" or
                                      p["adapter"] == "ace_opencode" and spec.get("preset_selection")))
        metadata = self.component_metadata.get(self.selections.get("Harness", ""), {})
        return (["AGENT_OPT_MODEL"] if self.selections.get("Agent") == "ace-rtl" and
                metadata.get("execution_mode") != "native" else [])

    def _required_model_fields(self) -> list[str]:
        from agent_optimizer.model_input import environment_snapshot
        values = {**environment_snapshot(), **self.model_values}
        if self.experiment:
            spec = load_experiment(self.experiment)
            profiles = spec["_profiles"]
            research = any(s["optimizer"] in {"gepa", "meta_harness", "ecdysis"}
                           for s in spec.get("stages", []))
            selectors = self._model_selector_fields(spec)
            api = research or any(p['adapter'] == 'ace_native' or p["adapter"] not in {"opencode", "ace_opencode"} and
                                  {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"}.issubset(
                                      p.get("runtime", {}).get("env_passthrough", [])) or
                                  p["adapter"] == "ace_opencode" and not spec.get("preset_selection") and
                                  {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"}.issubset(
                                      p.get("runtime", {}).get("env_passthrough", []))
                                  for p in profiles)
        else:
            metadata = self.component_metadata.get(self.selections.get("Harness", ""), {})
            selectors = self._model_selector_fields()
            api = (metadata.get("requires_model_api", False) or
                   self.selections.get("Agent") == "ace-rtl" and self.selections.get("Optimizer") != "baseline")
        fields = list(dict.fromkeys(selectors))
        if any(values.get(key) and (values[key].startswith("compatible/") or "/" not in values[key])
               for key in selectors):
            api = True
        if any(values.get(key, "").startswith("openrouter/") for key in selectors):
            fields.append("OPENROUTER_API_KEY")
        if api:
            fields += ["AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_ID", "AGENT_OPT_MODEL_API_KEY"]
        return list(dict.fromkeys(fields))

    def _missing_model_fields(self) -> list[str]:
        return [field for field in self._required_model_fields()
                if not self._model_value(field)[0]]

    def _needs_model_probe(self) -> bool:
        required = set(self._required_model_fields())
        fields = {"AGENT_OPT_MODEL_BASE_URL", "AGENT_OPT_MODEL_API_KEY"}
        return fields.issubset(required) and all(self._model_value(field)[0] for field in fields)

    def _external_call_summary(self) -> str:
        if self._needs_model_probe():
            return _tr("실행 전 모델 API probe 1회와 실행 중 외부 모델/Agent 호출",
                       "One model API probe before run; external model/Agent calls during run")
        if self._required_model_fields():
            return _tr("선택한 모델 provider가 실행 중 호출됩니다. 사전 connectivity probe는 수행하지 않습니다.",
                       "The selected model provider will be called during the run; no direct connectivity probe is available.")
        if self.experiment is not None:
            return _tr("선택한 Agent/Harness/Evaluator가 외부 서비스를 호출할 수 있습니다.",
                       "The selected Agent/Harness/Evaluator may call external services.")
        return _tr("Model API 호출 없음 · 합성 fixture 실행",
                   "No Model API call · synthetic fixture execution")

    def _start(self) -> None:
        try:
            fields = self._missing_model_fields()
        except (ConfigurationError, OSError) as exc:
            self._error(exc)
            return
        if fields:
            self._open_model_setup("Review")
        else:
            try:
                self._validate_model_selection()
            except ConfigurationError as exc:
                self._open_model_setup("Review")
                self._error(exc)
                return
            self._prepare()

    def _validate_model_selection(self) -> None:
        values = self._execution_environment()
        required = self._required_model_fields()
        if "AGENT_OPT_MODEL_BASE_URL" in required:
            validate_endpoint(values.get("AGENT_OPT_MODEL_BASE_URL", ""))
        selector = values.get("AGENT_OPT_MODEL", "")
        if "AGENT_OPT_MODEL" in required and self.selections.get("Agent") == "ace-rtl" and not (
                selector.startswith("compatible/") or selector.startswith("openrouter/")):
            raise ConfigurationError("OpenCode 모델은 compatible/모델 또는 openrouter/모델을 선택하세요")

    def _execution_environment(self) -> dict[str, str]:
        required = self._required_model_fields()
        from agent_optimizer.model_input import environment_snapshot
        values = {**environment_snapshot(), **{field: self._model_value(field)[0] for field in required}}
        for field in self._model_selector_fields():
            selector = values.get(field, "")
            if selector.startswith("compatible/") and selector.removeprefix("compatible/") != values.get("AGENT_OPT_MODEL_ID"):
                raise ConfigurationError(f"{field}의 compatible 모델과 AGENT_OPT_MODEL_ID가 일치해야 합니다. 선택자 또는 API ID를 수정하세요.")
        return values

    def action_open_report(self, report: Path, status: str = 'completed', *, row=None) -> None:
        self._report_epoch += 1
        self.report_work(report, row, self._report_epoch)

    @work(thread=True, group='report', exclusive=False)
    def report_work(self, report, row, epoch) -> None:
        from agent_optimizer.report_view import report_row, start_view, open_browser, view_status
        from agent_optimizer.history import verified_report
        handle = None
        try:
            row = row or report_row(report.parent, project_root=self.root)
            path = verified_report(row)
            with self._report_lock:
                if self._report_closing or epoch != self._report_epoch:
                    return
                if self._report_handle is not None:
                    self._report_handle.close()
                    self._report_handle = None
                if self._report_handle is None:
                    self._report_handle = start_view(row)
                    self._report_path = path
                handle = self._report_handle
            if not self._report_closing and epoch == self._report_epoch:
                self.call_from_thread(self._report_started,
                    f'HTML 보고서: {handle.url}\n브라우저: 열기 요청 중\nlocalhost는 실행 머신입니다. SSH에서는 포트포워딩이 필요합니다.')
            if self._report_closing or epoch != self._report_epoch:
                return
            opened = open_browser(handle.url)
            if not self._report_closing and epoch == self._report_epoch:
                self.call_from_thread(self._report_started, view_status(handle.url, opened))
        except Exception as exc:
            with self._report_lock:
                if epoch == self._report_epoch and self._report_handle is not None:
                    self._report_handle.close()
                    self._report_handle = None
            if not self._report_closing:
                self.call_from_thread(self._error, exc)

    def _report_started(self, text):
        self.set_home_status(text)
        self.query_one('#details', Static).update(text)
        if self.page == 'Result':
            self.query_one('#review', Static).update(self._result_text() + '\n' + text)

    async def on_unmount(self):
        import asyncio
        self._report_closing = True
        self._report_epoch += 1
        def close():
            with self._report_lock:
                if self._report_handle is not None:
                    self._report_handle.close()
                    self._report_handle = None
        await asyncio.to_thread(close)

    def set_home_status(self, text: str) -> None:
        """F hook for the active Home/report server status; no resource is created."""
        self.home_status = self._redact_secrets(text)
        self.query_one("#home-status", Static).update(self.home_status)

    def _prepare(self) -> None:
        self.busy = True
        self.preparation_error = None
        self.preparation_complete = False
        self.preparation_lines = []
        self._show("Preparing")
        self.prepare_work()

    @work(thread=True, exclusive=True)
    def prepare_work(self) -> None:
        from agent_optimizer.model_input import session_environment
        from agent_optimizer.preset_tui import (prepare_ace_selection, write_ace_selection,
                                                write_sample_selection)

        try:
            values = self._execution_environment()
            from agent_optimizer.app_paths import app_path
            app_path('experiments')
            with session_environment(values):
                if self.experiment is not None:
                    experiment = self.experiment
                    self.call_from_thread(
                        self._preparation_line,
                        _tr("기존 experiment 선택 · 자산 자동 준비 안 함",
                            "Existing experiment selected · no automatic asset preparation"))
                elif self.selections.get('Harness') == 'ace-native':
                    from agent_optimizer.native_selection import write_native_selection
                    experiment = write_native_selection(self.workspace, self.selections['Optimizer'], **{
                        key: Path(value) if key in {'dataset', 'source', 'upstream', 'python'} else value
                        for key, value in self.native_values.items() if value})
                elif self.selections["Agent"] == "ace-rtl":
                    capture = _ProgressCapture(self)
                    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                        assets = prepare_ace_selection(self.workspace)
                    capture.flush()
                    experiment = write_ace_selection(self.workspace, self.selections["Optimizer"], asset_root=assets)
                else:
                    capture = _ProgressCapture(self)
                    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                        experiment = write_sample_selection(
                            self.workspace, self.selections["Agent"], self.selections["Optimizer"],
                            progress_stream=capture)
                    capture.flush()
            self.call_from_thread(self._preparation_succeeded, experiment)
        except Exception as exc:
            self.call_from_thread(self._preparation_failed, exc)

    def _preparation_succeeded(self, experiment: Path) -> None:
        self.experiment = experiment
        self.busy = False
        self.preparation_complete = True
        self._show("Preparing")

    def _preparation_failed(self, exc: Exception) -> None:
        self.busy = False
        self.outcome = 2
        self.preparation_error = self._redact_secrets(str(exc)) or type(exc).__name__
        self._show("Preparing")

    def _check_doctor(self) -> None:
        self.busy = True
        self.doctor_report = None
        self.doctor_error = None
        self._show("Doctor")
        self.doctor_work()

    @work(thread=True, exclusive=True)
    def doctor_work(self) -> None:
        from agent_optimizer.model_input import session_environment
        from agent_optimizer.readiness import collect_plan
        from agent_optimizer.registry import Registry

        try:
            values = self._execution_environment()
            with session_environment(values):
                model_probe = self._needs_model_probe()
                report = collect_plan(self.experiment, Registry(), model=model_probe)
            self.call_from_thread(self._doctor_completed, report)
        except Exception as exc:
            self.call_from_thread(self._doctor_failed, exc)

    def _doctor_completed(self, report: dict) -> None:
        self.busy = False
        self.doctor_report = report
        self.doctor_error = None
        self.outcome = 0 if report.get("ready") else 2
        self._show("Doctor")

    def _doctor_failed(self, exc: Exception) -> None:
        self.busy = False
        self.outcome = 2
        self.doctor_report = None
        self.doctor_error = self._redact_secrets(str(exc)) or type(exc).__name__
        self._show("Doctor")

    def _run(self) -> None:
        try:
            spec = load_experiment(self.experiment)
        except (ConfigurationError, OSError, ValueError, KeyError, TypeError) as exc:
            self._finish({"status": "error", "reason": self._redact_secrets(str(exc))})
            return
        self.outcome = 0
        self.busy = True
        self.return_page = "Doctor"
        self.progress_state = ProgressState(spec.get("budget", {}).get("max_trials"))
        self.run_started_at = time.monotonic()
        self.run_status = "running"
        self.run_optimizer = (spec.get("preset_selection", {}).get("optimizer") or
                              self.selections.get("Optimizer") or
                              ", ".join(stage["optimizer"] for stage in spec.get("stages", [])) or "baseline")
        self.run_result = None
        self.run_failure_reason = None
        self.query_one("#event-log", RichLog).clear()
        self._show("Running")
        self._refresh_run_state()
        self.run_timer = self.set_interval(1.0, self._refresh_run_state)
        self.execute()

    def _refresh_run_state(self) -> None:
        if self.run_started_at is None:
            elapsed = "00:00"
        else:
            seconds = max(0, int(time.monotonic() - self.run_started_at))
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed = f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
        status = "● " + (_tr("실행 중", "RUNNING") if self.run_status == "running" else
                         human(self.run_status))
        state = self.progress_state
        iteration = (f"{state.iteration}/{state.total}" if state.iteration is not None and
                     state.total is not None else str(state.iteration or "-"))
        budget = (f"{state.completed}/{state.max_trials} " +
                  _tr("완료 · 최대 잔여", "completed · max remaining") + f" {state.remaining}"
                  if state.max_trials is not None else
                  f"{state.completed} " + _tr("완료", "completed"))
        text = "\n".join((
            status + f"  ·  {_tr('Optimizer', 'Optimizer')} {self.run_optimizer}",
            f"{_tr('단계', 'Stage')} {state.stage or '-'}  ·  "
            f"{_tr('반복', 'Iteration')} {iteration}",
            f"{_tr('작업', 'Task')} {state.task or '-'}  ·  "
            f"{_tr('Phase', 'Phase')} {state.phase or _tr('대기 중', 'waiting')}",
            f"{_tr('Trial budget', 'Trial budget')}: {budget}",
            f"{_tr('경과', 'Elapsed')}: {elapsed}",
        ))
        self.query_one("#run-state", Static).update(self._redact_secrets(text))

    def _handle_run_event(self, event: dict) -> None:
        if not self.progress_state.update(event):
            return
        if event.get("event") in {"error", "source_error", "budget_exhausted", "interrupted"}:
            detail = event.get("detail")
            failure = event.get("failure")
            if not detail and isinstance(failure, dict):
                detail = failure.get("detail")
            if detail:
                self.run_failure_reason = self._redact_secrets(detail)
        message = format_progress_event(event, humanize=True)
        if message is None:
            return
        timestamp = event.get("timestamp", "")
        clock = timestamp[11:19] if isinstance(timestamp, str) and len(timestamp) >= 19 else \
            time.strftime("%H:%M:%S")
        line = f"{clock}  {message}"
        if event.get("event") == "trial_completed":
            metrics = event.get("metrics", {})
            score = metrics.get("passed")
            duration = metrics.get("task_wall_time_seconds")
            if type(score) in {int, float} and math.isfinite(score):
                line += f" · passed={score:g}"
            if type(duration) in {int, float} and math.isfinite(duration) and duration >= 0:
                line += f" · {duration:.1f}s"
        line = self._redact_secrets(line)
        log = self.query_one("#event-log", RichLog)
        stay_at_end = log.is_vertical_scroll_end
        log.write(Text(line), scroll_end=False)
        if stay_at_end:
            log.scroll_end(animate=False)
        self._refresh_run_state()

    def _result_text(self) -> str:
        result = self.run_result or {}
        status = result.get("status", "error")
        state = self._run_status_label(status)
        title = (_tr("최적화 완료", "Optimization completed") if status == "completed" else
                 _tr("최적화 일부 완료", "Optimization partially completed") if status == "partial" else
                 _tr("최적화 실패", "Optimization failed"))
        lines = [title, "────────", f"  {_tr('상태', 'Status')}: {state}"]
        if result.get("trials_used") is not None:
            lines.append(f"  {_tr('사용한 trial', 'Trials used')}: {result['trials_used']}")
        if result.get("max_trials") is not None:
            lines.append(f"  {_tr('최대 budget', 'Trial budget maximum')}: {result['max_trials']}")
        if result.get("stage"):
            lines.append(f"  {_tr('단계', 'Stage')}: {result['stage']}")
        if result.get("exit_code") is not None:
            lines.append(f"  {_tr('종료 코드', 'Exit code')}: {result['exit_code']}")
        if result.get("reason"):
            lines += ["", _tr("실패 원인", "Reason"),
                      f"  {self._redact_secrets(result['reason'])}",
                      f"  {_tr('다음', 'Next')}: " + _tr(
                          "endpoint·네트워크·선택 설정을 확인한 뒤 다시 시도하세요.",
                          "Check the endpoint, network, and selected settings before retrying.")]
        elif status == "budget_exhausted":
            lines += ["", _tr("원인", "Reason"),
                      "  " + _tr("trial 또는 wall-time budget을 소진했습니다.",
                                 "The trial or wall-time budget was exhausted.")]
        elif status == "no_eligible_candidate":
            lines += ["", _tr("원인", "Reason"),
                      "  " + _tr("검증에서 선택 가능한 후보가 없습니다.",
                                 "No candidate was eligible after validation.")]
        if result.get("run_dir"):
            lines += ["", f"{_tr('실행 디렉터리', 'Run directory')}: {result['run_dir']}"]
        if result.get("report_html"):
            lines.append(f"{_tr('보고서', 'Report')}: {result['report_html']}")
        artifacts = result.get("artifacts", [])
        if artifacts:
            lines += ["", _tr("산출물", "Artifacts")]
            lines.extend(f"  {path}" for path in artifacts)
        return self._redact_secrets("\n".join(lines))

    def _run_status_label(self, status: str) -> str:
        return {
            "completed": _tr("완료", "Completed"),
            "partial": _tr("일부 완료", "Partial"),
            "interrupted": _tr("중단", "Interrupted"),
            "budget_exhausted": _tr("예산 소진", "Budget exhausted"),
            "no_eligible_candidate": _tr("선택 가능한 후보 없음", "No eligible candidate"),
            "source_error": _tr("소스 오류", "Source error"),
            "error": _tr("실패", "Failed"),
            "failed": _tr("실패", "Failed"),
        }.get(status, status)

    @work(thread=True, exclusive=True)
    def execute(self) -> None:
        from agent_optimizer.integrations import launch_existing
        from agent_optimizer.model_input import session_environment
        from agent_optimizer.preset_tui import execute_ace_selection
        from agent_optimizer.registry import Registry
        from agent_optimizer.runner import run_experiment
        from agent_optimizer.config import load_experiment

        try:
            values = self._execution_environment()
            with session_environment(values):
                spec = load_experiment(self.experiment)
                def on_event(event):
                    self.call_from_thread(self._handle_run_event, event)
                launched = launch_existing(spec, Registry())
                if launched is not None:
                    self.outcome = 0 if launched == 0 else 3
                    result = {"status": "completed" if launched == 0 else "failed",
                              "exit_code": launched,
                              "max_trials": spec.get("budget", {}).get("max_trials")}
                else:
                    if spec.get("preset_selection"):
                        run_dir, summary = execute_ace_selection(self.experiment, on_event=on_event)
                    else:
                        run_dir, summary = run_experiment(spec, Registry(), on_event=on_event)
                    self.outcome = 0 if summary["status"] == "completed" else 3
                    result = {"status": summary["status"], "trials_used": summary.get("trials_used"),
                              "max_trials": spec.get("budget", {}).get("max_trials"),
                              "run_dir": run_dir,
                              "artifacts": self._run_artifacts(run_dir),
                              "stage": self.progress_state.stage}
                    failure = summary.get("failure")
                    reason = summary.get("error")
                    if not reason and isinstance(failure, dict):
                        reason = failure.get("detail")
                        result["stage"] = failure.get("stage_id") or result["stage"]
                    if not reason:
                        reason = self.run_failure_reason
                    if reason:
                        result["reason"] = self._redact_secrets(reason)
                    artifacts = result["artifacts"]
                    result["report_html"] = next((path for path in artifacts
                                                   if path.name == "report.html"), None)
                self.call_from_thread(self._finish, result)
        except (ConfigurationError, UnavailableError, OSError, ValueError, KeyError, TypeError) as exc:
            self.outcome = 2
            self.call_from_thread(self._finish, self._failure_result(exc))
        except Exception as exc:
            self.outcome = 2
            self.log.error(self._redact_secrets(traceback.format_exc()))
            self.call_from_thread(self._finish, self._failure_result(exc))

    def _run_artifacts(self, run_dir: Path) -> list[Path]:
        return [path for path in (run_dir / name for name in
                                  ("report.html", "report.md", "summary.json", "events.jsonl"))
                if path.is_file() and not path.is_symlink()]

    def _failure_result(self, exc: Exception) -> dict:
        run_root = getattr(exc, "run_root", None)
        run_dir = Path(run_root) if isinstance(run_root, (str, os.PathLike)) and run_root else None
        failure = getattr(exc, "failure_diagnostic", None)
        failure = failure if isinstance(failure, dict) else {}
        artifacts = self._run_artifacts(run_dir) if run_dir else []
        return {"status": "failed", "reason": self._redact_secrets(str(exc)),
                "stage": failure.get("stage_id") or self.progress_state.stage,
                "run_dir": run_dir, "artifacts": artifacts,
                "report_html": next((path for path in artifacts if path.name == "report.html"), None),
                "max_trials": self.progress_state.max_trials}

    def _finish(self, result: dict) -> None:
        self.busy = False
        self.run_result = result
        self.run_status = result.get("status", "failed")
        if self.run_timer is not None:
            self.run_timer.stop()
            self.run_timer = None
        self._show("Result")

    def _error(self, exc: Exception) -> None:
        self.query_one("#details", Static).update(
            f"{_tr('설정 오류', 'Configuration Error')}\n\n{self._redact_secrets(human(str(exc)))}\n\n"
            + _tr("경로·선택 항목을 확인한 뒤 다시 시도하세요.", "Check the path or selection and try again."))

    def action_back(self) -> None:
        if self.busy:
            self.notify(_tr("준비/진단/실행 중입니다. 완료 후 계속할 수 있습니다.",
                            "Preparation, checks, or a run is active; wait for completion."))
            return
        entry = self.query_one("#entry", Input)
        if entry.has_focus and self.page in {"Existing", "Workspace"}:
            self._remember_input_draft(self.page, entry.value)
        elif entry.has_focus and self.page == "Model" and self.model_mode == "input":
            self._remember_input_draft(self.model_field, entry.value)
        if self.page == "Home":
            self.notify(_tr("시작 화면입니다. 종료하려면 q를 누르세요.", "At Home; press q to quit."))
        elif self.page in STEPS:
            self._show("Home" if self.page == "Agent" else STEPS[STEPS.index(self.page) - 1])
        elif self.page == "Review":
            self._show(self.return_page)
        elif self.page in {"Preparing", "Doctor"}:
            self._show("Review")
        elif self.page == "Result":
            self._show("Doctor")
        elif self.page == "Model":
            if self.model_mode == "input":
                self.model_mode = "choices"
                self.focus_indices["Model"] = 0
                self._show("Model")
            elif self.model_mode == "choices":
                self.model_mode = "fields"
                self.model_index = self.model_fields.index(self.model_field)
                self.focus_indices["Model"] = self.model_index
                self._show("Model")
            else:
                self._show(self.model_return_page)
        elif self.page == "Running":
            self._show("Home")
        elif self.page == "Workspace":
            self._show(self.workspace_back)
        elif self.page == 'Native':
            self._show('Dataset')
        elif self.page == 'NativeRows':
            self._show('Native')
        elif self.page == 'NativeSplit':
            self._show('NativeRows')
        elif self.page == 'SessionHistory':
            self._show('History')
        else:
            self._show("Home")

    def action_quit_app(self) -> None:
        if self.busy:
            self.notify(_tr("실행 중입니다. 완료 후 종료하세요.", "Running; quit after completion."))
        else:
            self.exit(self.outcome)
