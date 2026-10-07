"""선택형 입력 변경 전후 화면을 합성 데이터로 캡처한다."""
import argparse
import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.tui import OptimizerApp
from support import test_project, choose_row


def save(app, output, name, root):
    svg = app.export_screenshot().replace(str(root), '/fixture/project')
    (output / name).write_text('\n'.join(line.rstrip() for line in svg.splitlines()) + '\n', encoding='utf-8')


async def capture(output):
    output.mkdir(parents=True, exist_ok=True)
    temporary, root = test_project()
    try:
        environment = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'TMPDIR', 'AGENT_OPT_HOME'}}
        with patch.dict(os.environ, {**environment, 'AGENT_OPT_LANG': 'ko',
                'AGENT_OPT_MODEL_BASE_URL': 'https://model.example/v1', 'AGENT_OPT_MODEL_ID': 'fixture-model'}, clear=True):
            app = OptimizerApp(root)
            async with app.run_test(size=(100, 32)) as pilot:
                for page in ('Existing', 'Native', 'Advanced', 'Model'):
                    app.selections = {'Agent': 'ace-rtl', 'Harness': 'ace-native', 'Optimizer': 'gepa', 'Dataset': 'cvdp'}
                    app.model_fields = app._required_model_fields()
                    app._show(page)
                    await pilot.pause()
                    save(app, output, f'{page.lower()}.svg', root)
                if hasattr(app, 'advanced_values'):
                    for page, action, name in (('Existing', 'path.browse', 'browser'),
                            ('Native', 'cids', 'cids'), ('Native', 'evaluator', 'evaluator'),
                            ('Model', 'model.profile', 'profile')):
                        app._show(page)
                        await choose_row(app, pilot, action)
                        await pilot.pause()
                        save(app, output, f'{name}.svg', root)
                        await pilot.press('escape')
                    app.advanced_values['agent'] = str(root / 'examples/minimal/agents/solo')
                    app._show('Advanced')
                    await choose_row(app, pilot, 'editable')
                    await pilot.pause()
                    save(app, output, 'editable.svg', root)
                    await pilot.press('escape')
            app = OptimizerApp(root)
            async with app.run_test(size=(50, 20)) as pilot:
                app._show('Existing')
                if any(row.id == 'path.browse' for row in app.rows):
                    await choose_row(app, pilot, 'path.browse')
                    await pilot.pause()
                    save(app, output, 'browser-narrow.svg', root)
    finally:
        temporary.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    asyncio.run(capture(parser.parse_args().output))
