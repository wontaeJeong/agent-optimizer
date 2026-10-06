"""TUI 전용 탐색·다중 선택·항목별 입력. 선택 확정 전에는 파일을 쓰지 않는다."""
from __future__ import annotations

import os
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets import Button, Input, OptionList, Select, SelectionList, Static
from textual.widgets.option_list import Option


class PathSuggester(Suggester):
    def __init__(self, base: Path):
        super().__init__(use_cache=False, case_sensitive=True)
        self.base = base

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        path = Path(value).expanduser()
        path = path if path.is_absolute() else self.base / path
        try:
            matches = sorted(p for p in path.parent.iterdir() if p.name.startswith(path.name))
            if not matches:
                return None
            suffix = matches[0].name[len(path.name):] + ('/' if matches[0].is_dir() else '')
            return value + suffix if suffix else None
        except OSError:
            return None


class InputDialog(ModalScreen):
    BINDINGS = [Binding('escape', 'cancel', '취소', priority=True),
                Binding('ctrl+enter', 'apply', '적용', priority=True)]
    DEFAULT_CSS = """
    InputDialog { align: center middle; background: $background 70%; }
    InputDialog > Vertical { width: 90%; max-width: 100; height: 90%;
        border: round $accent; background: $surface; padding: 1 2; }
    InputDialog .dialog-title { height: auto; text-style: bold; margin-bottom: 1; }
    InputDialog .dialog-help { height: auto; color: $text-muted; }
    InputDialog Horizontal { height: auto; }
    InputDialog Button { margin: 0 1 0 0; }
    InputDialog #dialog-error { height: auto; color: $error; }
    InputDialog VerticalScroll { height: 1fr; }
    InputDialog Input { margin-bottom: 1; }
    InputDialog .field-row Input { width: 1fr; }
    InputDialog #path-project, InputDialog #path-home, InputDialog #path-parent { min-width: 8; width: 1fr; }
    InputDialog.compact > Vertical { width: 100%; height: 100%; padding: 0 1; }
    InputDialog.compact .dialog-title { margin-bottom: 0; }
    InputDialog.compact Input { margin-bottom: 0; }
    InputDialog.compact .dialog-help { display: none; }
    InputDialog OptionList { height: 1fr; min-height: 3; }
    """

    def on_resize(self, event):
        self.set_class(event.size.width < 76 or event.size.height < 26, 'compact')

    def action_cancel(self):
        self.dismiss(None)

    def on_input_changed(self, event: Input.Changed):
        event.stop()

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        self.action_apply()

    def on_option_list_option_highlighted(self, event):
        event.stop()

    def error(self, message):
        self.query_one('#dialog-error', Static).update(Text(str(message)))


class PathDialog(InputDialog):
    """Lazy one-directory-at-a-time browsing; no recursive Home scan."""

    BINDINGS = [*InputDialog.BINDINGS, Binding('ctrl+l', 'location', '경로'),
                Binding('alt+up', 'parent', '상위 폴더')]

    def __init__(self, base: Path, *, title='경로 선택', directory=False, suffix=None, value=''):
        super().__init__()
        self.base = base
        self.title = title
        self.directory = directory
        self.suffix = suffix
        self.initial = value
        self.paths: list[Path] = []
        self.current = base

    def compose(self):
        with Vertical():
            yield Static(Text(self.title), classes='dialog-title')
            yield Input(self.initial or str(self.base), id='path-value', suggester=PathSuggester(self.base))
            with Horizontal():
                yield Button('프로젝트', id='path-project')
                yield Button('Home', id='path-home')
                yield Button('상위 폴더', id='path-parent')
            yield Static('↑↓ 탐색 · Enter 폴더 열기/파일 선택 · → 경로 자동완성 · Esc 취소', classes='dialog-help')
            yield OptionList(id='path-options')
            yield Static('', id='dialog-error')
            with Horizontal():
                yield Button('현재 폴더 선택' if self.directory else '경로 선택', id='path-apply', variant='primary')
                yield Button('취소', id='path-cancel')

    def on_mount(self):
        path = self.resolve(self.initial) if self.initial else self.base
        self.open_directory(path if path.is_dir() else path.parent)
        self.query_one('#path-options').focus()

    def resolve(self, value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.base / path

    def open_directory(self, path):
        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            self.paths = [path.parent] + [p for p in children if p.name != '.git' and
                (not p.name.startswith('.') or p.is_dir()) and
                (p.is_dir() or not self.directory and (self.suffix is None or p.suffix in self.suffix))]
        except OSError as exc:
            self.error(f'폴더를 열 수 없습니다: {exc}')
            return
        self.current = path.absolute()
        self.query_one('#path-value', Input).value = str(self.current)
        self.query_one('#path-options', OptionList).set_options([
            Option(Text('.. / 상위 폴더' if i == 0 else ('▸ ' if p.is_dir() else '  ') + p.name))
            for i, p in enumerate(self.paths)])
        self.error('')

    def on_option_list_option_selected(self, event):
        event.stop()
        path = self.paths[event.option_index]
        if path.is_dir():
            self.open_directory(path)
        else:
            self.dismiss(path.absolute())

    def on_input_submitted(self, event):
        event.stop()
        path = self.resolve(event.value.strip())
        if path.is_dir():
            self.open_directory(path)
            self.query_one('#path-options').focus()
        else:
            self.action_apply()

    def action_apply(self):
        path = self.resolve(self.query_one('#path-value', Input).value.strip())
        if not (path.is_dir() if self.directory else path.is_file()):
            self.error('존재하는 폴더를 선택하세요.' if self.directory else '존재하는 파일을 선택하세요.')
        elif not self.directory and self.suffix is not None and path.suffix not in self.suffix:
            self.error('이 설정에서 지원하는 파일 형식을 선택하세요.')
        else:
            self.dismiss(path.absolute())

    def on_button_pressed(self, event):
        event.stop()
        button = event.button.id
        if button == 'path-apply':
            self.action_apply()
        elif button == 'path-project':
            self.open_directory(self.base)
        elif button == 'path-home':
            self.open_directory(Path.home())
        elif button == 'path-parent':
            self.action_parent()
        else:
            self.action_cancel()

    def action_location(self):
        self.query_one('#path-value').focus()

    def action_parent(self):
        self.open_directory(self.current.parent)


class ChoiceDialog(InputDialog):
    def __init__(self, title, items, *, selected=(), multiple=False):
        super().__init__()
        self.title = title
        self.items = list(items)  # (stable value, label)
        self.filtered_items = list(items)
        self.chosen = set(selected)
        self.multiple = multiple

    def compose(self):
        with Vertical():
            yield Static(Text(self.title), classes='dialog-title')
            yield Input(placeholder='이름·ID 검색', id='choice-search')
            yield Static('Space 선택/해제 · Ctrl+Enter 적용 · Esc 취소' if self.multiple else
                         '↑↓ 탐색 · Enter 선택 · Esc 취소', classes='dialog-help')
            if self.multiple:
                yield SelectionList(*[(Text(label), value, value in self.chosen) for value, label in self.items], id='choice-options')
            else:
                yield OptionList(*[Option(Text(label), id=str(value)) for value, label in self.items], id='choice-options')
            yield Static('', id='dialog-error')
            with Horizontal():
                yield Button('선택 적용', id='choice-apply', variant='primary')
                yield Button('취소', id='choice-cancel')

    def on_mount(self):
        self.query_one('#choice-options').focus()

    def remember(self):
        if self.multiple:
            visible_ids = {value for value, _ in self.filtered_items}
            self.chosen.difference_update(visible_ids)
            self.chosen.update(self.query_one(SelectionList).selected)

    def on_input_changed(self, event):
        event.stop()
        if event.input.id != 'choice-search':
            return
        self.remember()
        term = event.value.casefold()
        self.filtered_items = [(value, label) for value, label in self.items if term in label.casefold() or term in str(value).casefold()]
        options = self.query_one('#choice-options')
        options.clear_options()
        if self.multiple:
            options.add_options([(Text(label), value, value in self.chosen) for value, label in self.filtered_items])
        else:
            options.add_options([Option(Text(label), id=str(value)) for value, label in self.filtered_items])

    def on_input_submitted(self, event):
        event.stop()
        self.query_one('#choice-options').focus()

    def on_option_list_option_selected(self, event):
        event.stop()
        if not self.multiple:
            self.dismiss(self.filtered_items[event.option_index][0])

    def action_apply(self):
        if self.multiple:
            self.remember()
            self.dismiss([value for value, _ in self.items if value in self.chosen])
        else:
            index = self.query_one('#choice-options', OptionList).highlighted
            if index is not None and index < len(self.filtered_items):
                self.dismiss(self.filtered_items[index][0])

    def on_button_pressed(self, event):
        event.stop()
        self.action_apply() if event.button.id == 'choice-apply' else self.action_cancel()


class FormDialog(InputDialog):
    """Fields: (id, label, value, kind), kind=text/file/directory or choices."""

    def __init__(self, title, fields, *, base: Path, validate=None):
        super().__init__()
        self.title = title
        self.fields = fields
        self.base = base
        self.validate = validate

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(Text(self.title), classes='dialog-title')
            yield Static('Tab 다음 항목 · Ctrl+Enter 적용 · Esc 취소', classes='dialog-help')
            with VerticalScroll():
                for key, label, value, kind in self.fields:
                    value = getattr(self.app, 'form_drafts', {}).get((self.title, key), value)
                    yield Static(Text(label))
                    if isinstance(kind, (list, tuple)):
                        yield Select([(str(item), item) for item in kind], value=value or Select.BLANK, id=f'field-{key}')
                    else:
                        with Horizontal(classes='field-row'):
                            if kind in {'endpoint', 'git'}:
                                from agent_optimizer.tui import ModelInput
                                entry = ModelInput(str(value or ''), id=f'field-{key}')
                                entry.endpoint_mode = kind == 'endpoint'
                                entry.git_mode = kind == 'git'
                                yield entry
                            else:
                                yield Input(str(value or ''), id=f'field-{key}', suggester=PathSuggester(self.base) if kind in {'file', 'directory'} else None)
                            if kind in {'file', 'directory'}:
                                yield Button('탐색', id=f'browse-{key}')
            yield Static('', id='dialog-error')
            with Horizontal():
                yield Button('적용', id='form-apply', variant='primary')
                yield Button('취소', id='form-cancel')

    def on_input_changed(self, event):
        event.stop()
        if hasattr(self.app, 'form_drafts'):
            self.app.form_drafts[(self.title, event.input.id.removeprefix('field-'))] = event.value

    def on_model_input_endpoint_rejected(self, event):
        event.stop()
        self.error('자격증명 포함 URL을 제거했습니다. API key는 별도로 입력하세요.')

    def on_select_changed(self, event):
        event.stop()
        if hasattr(self.app, 'form_drafts'):
            self.app.form_drafts[(self.title, event.select.id.removeprefix('field-'))] = (
                '' if event.value is Select.BLANK else event.value)

    def on_button_pressed(self, event):
        event.stop()
        button = event.button.id
        if button == 'form-apply':
            self.action_apply()
        elif button == 'form-cancel':
            self.action_cancel()
        elif button.startswith('browse-'):
            key = button.removeprefix('browse-')
            kind = next(kind for name, _, _, kind in self.fields if name == key)
            entry = self.query_one(f'#field-{key}', Input)
            def receive(path):
                if path is not None:
                    entry.value = str(path)
            self.app.push_screen(PathDialog(self.base, directory=kind == 'directory', value=entry.value), receive)

    def action_apply(self):
        values = {}
        for key, _, _, kind in self.fields:
            widget = self.query_one(f'#field-{key}')
            value = widget.value
            if value is not Select.BLANK and str(value).strip():
                values[key] = str(value).strip()
        try:
            if self.validate:
                self.validate(values)
        except (ValueError, OSError) as exc:
            self.error(exc)
            return
        if hasattr(self.app, 'form_drafts'):
            for key, _, _, _ in self.fields:
                self.app.form_drafts.pop((self.title, key), None)
        self.dismiss(values)


class SplitDialog(InputDialog):
    def compose(self):
        with Vertical():
            yield Static('명시적으로 고른 row에 적용할 split', classes='dialog-title')
            yield Static('train: 수정 근거 · validation: 후보 비교 · test: 선택 고정 이후 평가', classes='dialog-help')
            with VerticalScroll():
                for split in ('train', 'validation', 'test', 'remove'):
                    yield Button('선택 해제' if split == 'remove' else split, id=f'split-{split}')
            yield Button('취소', id='split-cancel')

    def action_apply(self):
        pass

    def on_button_pressed(self, event):
        event.stop()
        self.dismiss(None if event.button.id == 'split-cancel' else event.button.id.removeprefix('split-'))


def editable_files(root: Path) -> list[str]:
    """Only inspect the explicitly chosen Agent; skip credentials and tool state."""
    ignored = {'.git', '.venv', 'node_modules', '__pycache__', '.worktrees'}
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ignored and not d.startswith('.') and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if not name.startswith('.') and not path.is_symlink():
                files.append(path.relative_to(root).as_posix())
    return files
