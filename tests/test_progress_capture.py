"""준비 로그는 UI·worker 어느 스레드에서 써도 안전하게 전달되어야 한다."""
import asyncio
import unittest

from agent_optimizer.tui import OptimizerApp, _ProgressCapture
from support import test_project


class PreparationCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_ui_and_worker_lines_and_flush_reach_ui_without_secret(self):
        temporary, project = test_project()
        self.addCleanup(temporary.cleanup)
        app = OptimizerApp(project)
        app.model_values['AGENT_OPT_MODEL_API_KEY'] = 'capture-secret-sentinel'
        async with app.run_test() as pilot:
            app._show('Preparing')
            capture = _ProgressCapture(app)
            try:
                capture.write('UI capture-secret-sentinel\n')
                capture.write('UI flush')
                capture.flush()
                await asyncio.to_thread(capture.write, 'worker complete\n')
                await asyncio.to_thread(capture.write, 'worker flush')
                await asyncio.to_thread(capture.flush)
            except RuntimeError as exc:
                self.fail(f'로그 발신 스레드에 따른 준비 진행 전달 실패: {exc}')
            await pilot.pause()
            lines = '\n'.join(app.preparation_lines)
            for label in ('UI', 'UI flush', 'worker complete', 'worker flush'):
                self.assertIn(label, lines)
            self.assertNotIn('capture-secret-sentinel', lines)
            self.assertEqual(len(app.preparation_lines), 4)
