"""실행 argv·캐시 게시 경계에서 Docker 레이어 재사용을 검증한다."""
import tempfile
import os
import sys
import subprocess
import threading
import unittest
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.network import configured_build


class BuildCacheTests(unittest.TestCase):
    def test_export_is_reused_without_changing_image_or_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {"AGENT_OPT_BUILD_CACHE_DIR": str(root / "cache")}
            argv = ["docker", "build", "--platform", "linux/amd64", "-t", "fixture", "."]
            with configured_build(argv, root, env) as command:
                self.assertEqual(command[:4], ["docker", "buildx", "build", "--load"])
                self.assertEqual(command[-len(argv[2:]):], argv[2:])
                self.assertNotIn("--cache-from", command)
                destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                destination.mkdir()
                (destination / "index.json").write_text("first build")
            with configured_build(argv, root, env) as command:
                source = Path(command[command.index("--cache-from") + 1].split("src=", 1)[1])
                self.assertEqual((source / "index.json").read_text(), "first build")
                destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                destination.mkdir()
                (destination / "index.json").write_text("second build")
            self.assertEqual((source / "index.json").read_text(), "second build")
            self.assertEqual(len([path for path in (root / "cache").iterdir()
                                  if not path.name.startswith(".")]), 1)

    def test_failed_build_never_publishes_partial_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {"AGENT_OPT_BUILD_CACHE_DIR": str(root / "cache")}
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                with configured_build(["docker", "build", "-t", "fixture", "."], root, env) as command:
                    destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                    destination.mkdir()
                    (destination / "index.json").write_text("partial")
                    raise RuntimeError("build failed")
            self.assertEqual([path for path in (root / "cache").iterdir()
                              if not path.name.startswith(".")], [])

    def test_invalid_cache_path_is_rejected_before_build(self):
        for value in ("relative/cache", "/tmp/bad,cache", "/tmp/bad\ncache"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                with configured_build(["docker", "build", "-t", "fixture", "."], Path("."),
                                      {"AGENT_OPT_BUILD_CACHE_DIR": value}):
                    pass

    def test_nonbuild_command_does_not_touch_cache(self):
        argv = ["docker", "image", "inspect", "fixture"]
        with configured_build(argv, Path("."), {"AGENT_OPT_BUILD_CACHE_DIR": "invalid"}) as command:
            self.assertEqual(command, argv)

    def test_network_cli_keeps_failed_exit_code_and_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            argv = ["docker", "build", "-t", "fixture", "."]
            env = {**os.environ, "AGENT_OPT_BUILD_CACHE_DIR": str(root / "cache")}
            env.pop("AGENT_OPT_CA_BUNDLE", None)
            with configured_build(argv, root, env) as command:
                destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                destination.mkdir()
                (destination / "index.json").write_text("original")
            source = next(path for path in (root / "cache").iterdir() if not path.name.startswith("."))
            script = Path(__file__).resolve().parents[1] / "scripts/network.py"
            for export in (True, False):
                (root / "docker").write_text(
                    f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\n"
                    "destination = Path(sys.argv[sys.argv.index('--cache-to') + 1].split('dest=', 1)[1].split(',')[0])\n"
                    + ("destination.mkdir()\n(destination / 'index.json').write_text('partial')\n" if export else "")
                    + "raise SystemExit(7)\n")
                (root / "docker").chmod(0o755)
                result = subprocess.run([sys.executable, str(script), "--", *argv], cwd=root,
                                        env={**env, "PATH": str(root) + os.pathsep + env.get("PATH", "")},
                                        capture_output=True, text=True, timeout=10, shell=False)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual((source / "index.json").read_text(), "original")

    def test_same_image_cache_is_locked_until_export_is_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {"AGENT_OPT_BUILD_CACHE_DIR": str(root / "cache")}
            argv = ["docker", "build", "-t", "fixture", "."]
            entered = threading.Event()
            errors = []
            def second():
                try:
                    with configured_build(argv, root, env) as command:
                        entered.set()
                        source = Path(command[command.index("--cache-from") + 1].split("src=", 1)[1])
                        self.assertEqual((source / "index.json").read_text(), "first")
                        destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                        destination.mkdir()
                        (destination / "index.json").write_text("second")
                except Exception as exc:
                    errors.append(exc)
            with configured_build(argv, root, env) as command:
                thread = threading.Thread(target=second)
                thread.start()
                self.assertFalse(entered.wait(0.1), "concurrent import crossed publication boundary")
                destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                destination.mkdir()
                (destination / "index.json").write_text("first")
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])

    def test_symlinked_cache_index_is_not_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {"AGENT_OPT_BUILD_CACHE_DIR": str(root / "cache")}
            argv = ["docker", "build", "-t", "fixture", "."]
            with configured_build(argv, root, env) as command:
                destination = Path(command[command.index("--cache-to") + 1].split("dest=", 1)[1].split(",")[0])
                destination.mkdir()
                (destination / "index.json").write_text("original")
            source = next(path for path in (root / "cache").iterdir() if not path.name.startswith("."))
            (root / "outside").write_text("sentinel")
            (source / "index.json").unlink()
            (source / "index.json").symlink_to(root / "outside")
            with self.assertRaises(ConfigurationError):
                with configured_build(argv, root, env):
                    raise AssertionError("symlinked cache reached the build")
            self.assertEqual((root / "outside").read_text(), "sentinel")
