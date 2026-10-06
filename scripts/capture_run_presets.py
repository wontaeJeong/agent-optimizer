"""실행 프리셋의 실제 TUI 화면을 SVG로 캡처한다(모델 호출 없음)."""
import asyncio
import sys
from pathlib import Path

from textual.widgets import OptionList

from agent_optimizer.tui import OptimizerApp


def save(app, output, name):
    app.save_screenshot(filename=name, path=str(output))
    file = output / name
    file.write_text('\n'.join(line.rstrip() for line in file.read_text().splitlines()) + '\n')


async def main():
    output = Path(sys.argv[1])
    app = OptimizerApp(Path(__file__).resolve().parents[1])
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        save(app, output, f'run-presets-{sys.argv[2]}-home.svg')
        if any(row.id == 'presets' for row in app.rows):
            options = app.query_one(OptionList)
            options.highlighted = options.get_option_index('presets')
            await pilot.press('enter')
            options.highlighted = options.get_option_index('native-cid002-gepa')
            await pilot.pause()
            save(app, output, 'run-presets-after-selection.svg')


if __name__ == '__main__':
    asyncio.run(main())
