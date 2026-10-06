"""CI 실행기의 누락·실패 은폐·프로세스 격리 회귀를 검증한다."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "scripts/run_tests.py"


class CIRunnerTests(unittest.TestCase):
    def run_fixture(self, sources, jobs=2):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in sources.items():
                (root / name).write_text(source, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RUNNER), "--directory", str(root), "--jobs", str(jobs)],
                capture_output=True, text=True, timeout=20, shell=False,
            )
            summaries = [line.removeprefix("CI_SUMMARY ") for line in result.stdout.splitlines()
                         if line.startswith("CI_SUMMARY ")]
            return result, json.loads(summaries[-1]) if summaries else None

    def test_every_test_runs_once_and_skips_are_counted(self):
        result, summary = self.run_fixture({
            "test_a.py": "import unittest\nclass A(unittest.TestCase):\n"
                         " def test_pass(self): print('UNIQUE_A')\n"
                         " @unittest.skip('fixture')\n def test_skip(self): pass\n",
            "test_b.py": "import unittest\nclass B(unittest.TestCase):\n"
                         " def test_pass(self): print('UNIQUE_B')\n",
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("UNIQUE_A"), 1)
        self.assertEqual(result.stdout.count("UNIQUE_B"), 1)
        self.assertEqual(summary["tests"], 3)
        self.assertEqual(summary["skipped"], 1)

    def test_failure_and_import_error_both_fail_the_command(self):
        for source in (
            "import unittest\nclass A(unittest.TestCase):\n"
            " def test_fail(self): self.fail('VISIBLE_FAILURE')\n",
            "raise RuntimeError('VISIBLE_FAILURE')\n",
        ):
            with self.subTest(source=source):
                result, summary = self.run_fixture({"test_bad.py": source})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("VISIBLE_FAILURE", result.stdout + result.stderr)
                self.assertEqual(summary["tests"], 1)

    def test_workers_overlap_and_have_distinct_processes(self):
        sources = {}
        for own, other in (("a", "b"), ("b", "a")):
            sources[f"test_{own}.py"] = (
                "import os, time, unittest\nfrom pathlib import Path\n"
                "class A(unittest.TestCase):\n def test_overlap(self):\n"
                "  root = Path(__file__).parent\n"
                f"  (root / '{own}.pid').write_text(str(os.getpid()))\n"
                "  deadline = time.monotonic() + 5\n"
                f"  while not (root / '{other}.pid').exists() and time.monotonic() < deadline:\n"
                "   time.sleep(0.01)\n"
                f"  self.assertTrue((root / '{other}.pid').exists(), 'worker never overlapped')\n"
                f"  self.assertNotEqual((root / '{other}.pid').read_text(), str(os.getpid()))\n"
            )
        result, summary = self.run_fixture(sources)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(summary["tests"], 2)

    def test_empty_discovery_is_an_error(self):
        result, _ = self.run_fixture({})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("테스트", result.stdout + result.stderr)

    def test_repository_imports_work_without_pythonpath(self):
        result, summary = self.run_fixture({
            "test_import.py": "import unittest\nfrom examples.benchmarks.verilog_eval import REVISION\n"
                              "class A(unittest.TestCase):\n"
                              " def test_import(self): self.assertTrue(REVISION)\n",
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(summary["tests"], 1)

    def test_worker_crash_without_report_fails_the_command(self):
        result, summary = self.run_fixture({"test_crash.py": "import os\nos._exit(7)\n"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(summary["tests"], 0)

    def test_cancel_terminates_workers_and_term_resistant_descendants(self):
        for signum in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=signum), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                child_code = (
                    "import os, signal, time; from pathlib import Path; "
                    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                    f"Path({str(root / 'child.pid')!r}).write_text(str(os.getpid())); time.sleep(30)"
                )
                (root / "test_wait.py").write_text(
                    "import os, subprocess, sys, time, unittest\nfrom pathlib import Path\n"
                    "class A(unittest.TestCase):\n def test_wait(self):\n"
                    "  Path(__file__).with_name('worker.pid').write_text(str(os.getpid()))\n"
                    f"  subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
                    "  time.sleep(30)\n", encoding="utf-8",
                )
                runner = subprocess.Popen(
                    [sys.executable, str(RUNNER), "--directory", str(root)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False,
                )
                pids = []
                try:
                    deadline = time.monotonic() + 5
                    while not (root / "child.pid").exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue((root / "child.pid").exists(), "fixture did not start")
                    pids = [int((root / name).read_text()) for name in ("worker.pid", "child.pid")]
                    runner.send_signal(signum)
                    runner.communicate(timeout=6)
                    self.assertEqual(runner.returncode, 128 + signum)
                    for pid in pids:
                        deadline = time.monotonic() + 2
                        while self.process_running(pid) and time.monotonic() < deadline:
                            time.sleep(0.01)
                        self.assertFalse(self.process_running(pid), f"cancel left process {pid} running")
                finally:
                    if runner.poll() is None:
                        runner.kill()
                    runner.communicate()
                    for pid in pids:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    @staticmethod
    def process_running(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        stat = Path(f"/proc/{pid}/stat")
        # Linux may retain an orphan's zombie until the runner's init reaps it.
        return not stat.exists() or stat.read_text().split(") ", 1)[1].split()[0] != "Z"
