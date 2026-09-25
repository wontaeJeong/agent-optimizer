"""Exercise real shell/Make routing; replace only external installers and tools."""
import io
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_optimizer.contracts import UnavailableError
from support import ROOT, module


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="onboarding space ")
        self.addCleanup(temporary.cleanup)
        self.outside = Path(temporary.name).resolve()
        self.root = self.outside / "repo with spaces"
        (self.root / "scripts").mkdir(parents=True)
        for name in ("scripts/bootstrap.sh", "Makefile"):
            if (ROOT / name).exists():
                shutil.copyfile(ROOT / name, self.root / name)
        self.bin = self.outside / "bin"
        self.bin.mkdir()
        for name in ("sh", "dirname", "uname", "mkdir", "mktemp", "rm", "chmod", "cp", "sleep", "date", "ps", "awk"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.trace = self.outside / "trace"
        self.environment = {
            "PATH": str(self.bin), "HOME": str(self.outside), "TMPDIR": str(self.outside), "TRACE": str(self.trace),
            "TEMPLATE": str(self.outside / "python-template"),
            "UV_TEMPLATE": str(self.outside / "uv-template"),
            "INSTALLER": str(self.outside / "installer"), "KEEP_ME": "preserved value",
        }
        self.write_executable(self.outside / "python-template", '''
case "$1" in -I) exit 0;; esac
printf 'python:%s:%s:%s\\n' "$0" "$KEEP_ME" "${AGENT_OPT_BOOTSTRAPPED:-}" >> "$TRACE"
printf 'arg:%s\\n' "$@" >> "$TRACE"
exit 0
''')
        self.write_executable(self.outside / "uv-template", '''
printf 'uv:%s:%s\\n' "$UV_PROJECT_ENVIRONMENT" "${UV_PYTHON_DOWNLOADS:-}" >> "$TRACE"
printf 'arg:%s\\n' "$@" >> "$TRACE"
mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
if [ ! -e "$UV_PROJECT_ENVIRONMENT/bin/python" ]; then
    cp "$TEMPLATE" "$UV_PROJECT_ENVIRONMENT/bin/python"
fi
''')
        self.write_executable(self.outside / "installer", '''
printf 'installer:%s:%s\\n' "$UV_INSTALL_DIR" "$UV_NO_MODIFY_PATH" >> "$TRACE"
mkdir -p "$UV_INSTALL_DIR"
cp "$UV_TEMPLATE" "$UV_INSTALL_DIR/uv"
''')

    def write_executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)

    def tool(self, name, body="exit 0\n"):
        self.write_executable(self.bin / name, body)

    def prerequisites(self):
        self.tool("git")
        self.tool("docker")

    def uv(self):
        shutil.copyfile(self.outside / "uv-template", self.bin / "uv")
        (self.bin / "uv").chmod(0o755)

    def invoke(self, *args, make=False):
        if make:
            command = [shutil.which("make"), "-f", str(self.root / "Makefile"), *args]
        else:
            command = ["/bin/sh", str(self.root / "scripts/bootstrap.sh"), *args]
        return subprocess.run(command, cwd=self.outside, env=self.environment,
                              capture_output=True, text=True, timeout=20)

    def trace_text(self):
        return self.trace.read_text() if self.trace.exists() else ""

    def test_help_and_make_default_work_without_python_or_tools_from_foreign_cwd(self):
        for args, make in (((), False), (("help",), False), ((), True), (("help",), True)):
            with self.subTest(args=args, make=make):
                result = self.invoke(*args, make=make)
                self.assertEqual(result.returncode, 0, result.stderr)
                for command in ("setup", "doctor", "test", "lint", "demo", "smoke", "live", "menu"):
                    self.assertIn(command, result.stdout)
                self.assertIn("make setup ARGS=", result.stdout)
                self.assertIn("ACE 전체", result.stdout)
        self.assertFalse((self.root / ".venv").exists())
        self.assertEqual(self.trace_text(), "")

    def test_model_and_iteration_flags_reach_python_without_installing(self):
        self.tool("python3", 'case "$1" in -I) exit 0;; esac\nprintf "arg:%s\\n" "$@" >> "$TRACE"\n')
        for args in (("doctor", "--model", "--json"), ("live", "--iterations", "3")):
            result = self.invoke(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            for arg in args:
                self.assertIn("arg:" + arg, self.trace_text())
        self.assertFalse((self.root / ".venv").exists())
        self.assertEqual(self.invoke("live", "--iterations", "0").returncode, 2)

    def test_core_commands_do_not_select_demo_ca_implicitly(self):
        self.tool("python3", 'case "$1" in -I) exit 0;; esac\nprintf "ca:%s\\n" "${AGENT_OPT_CA_BUNDLE-unset}" >> "$TRACE"\n')
        self.environment.pop("AGENT_OPT_CA_BUNDLE", None)
        for command in ("test", "lint", "demo"):
            result = self.invoke(command)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trace_text().splitlines(), ["ca:unset"] * 3)

    def test_missing_buildx_blocks_ca_setup_before_installation(self):
        self.prerequisites()
        self.tool("docker", 'case "$1" in buildx) exit 1;; *) exit 0;; esac\n')
        bundle = self.outside / "bundle.pem"
        bundle.write_text("fixture")
        self.environment["AGENT_OPT_CA_BUNDLE"] = str(bundle)
        result = self.invoke("setup")
        self.assertEqual(result.returncode, 2)
        self.assertIn("docker-buildx-plugin", result.stderr)
        self.assertEqual(self.trace_text(), "")

    def test_core_setup_without_docker_or_python_reuses_uv_installer_and_frozen_sync(self):
        self.tool("git")
        self.downloader(0)
        result = self.invoke("setup", "--core")
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace_text()
        self.assertIn("installer:", trace)
        self.assertIn("arg:sync\narg:--frozen\n", trace)
        self.assertIn("arg:--extra\narg:dev\n", trace)
        self.assertIn("arg:setup\narg:--core\n", trace)

    def test_core_offline_sync_without_docker_never_downloads(self):
        self.tool("git")
        self.tool("curl", 'printf download >> "$TRACE"; exit 1\n')
        self.uv()
        result = self.invoke("setup", "--core", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"uv:{self.root}/.venv:never", self.trace_text())
        self.assertIn("arg:--offline\narg:sync\narg:--frozen\n", self.trace_text())
        self.assertNotIn("download", self.trace_text())

    def test_setup_sync_reports_elapsed_while_child_is_still_running_on_tty(self):
        self.tool("git")
        template = self.outside / "uv-template"
        template.write_text(template.read_text() + "sleep 2\n")
        self.uv()
        master, slave = pty.openpty()
        process = subprocess.Popen(["sh", str(self.root / "scripts/bootstrap.sh"), "setup", "--core"],
                                   cwd=self.outside, env=self.environment, stdout=subprocess.PIPE,
                                   stderr=slave, text=True)
        os.close(slave)
        observed = ""
        try:
            started = time.monotonic()
            while "elapsed=" not in observed and time.monotonic() - started < 6:
                readable, _, _ = select.select([master], [], [], 0.5)
                if readable:
                    try:
                        observed += os.read(master, 4096).decode(errors="replace")
                    except OSError:
                        break
            self.assertIn("elapsed=", observed)
            self.assertIsNone(process.poll(), "status arrived only after uv finished")
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            os.close(master)

    def test_core_still_requires_git_and_offline_uv(self):
        result = self.invoke("setup", "--core")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Git unavailable", result.stderr)
        self.assertNotIn("Docker", result.stderr)
        self.tool("git")
        result = self.invoke("setup", "--core", "--offline")
        self.assertEqual(result.returncode, 2)
        self.assertIn("uv missing", result.stderr)
        self.assertIn("setup --core", result.stderr)
        self.assertEqual(self.trace_text(), "")

    def test_core_sync_failure_preserves_scope_in_repair_and_never_probes_docker(self):
        self.tool("git")
        self.tool("docker", 'printf docker >> "$TRACE"; exit 1\n')
        self.tool("uv", "exit 7\n")
        for options in (("--core",), ("--core", "--offline")):
            with self.subTest(options=options):
                result = self.invoke("setup", *options)
                self.assertEqual(result.returncode, 2)
                self.assertIn("project-uv.log", result.stderr)
                self.assertIn("setup --core", result.stderr)
                self.assertNotIn("docker", self.trace_text())

    def test_core_conflicts_rejected_before_probes_and_missing_python_remedy_is_core(self):
        for args in (("setup", "--core", "--platform", "linux/amd64"),
                     ("doctor", "--platform=linux/arm64", "--core"),
                     ("doctor", "--model", "--core")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("--core cannot", result.stderr)
        for command in ("demo", "test", "lint", "smoke", "live", "menu"):
            self.assertEqual(self.invoke(command, "--core").returncode, 2)
        result = self.invoke("doctor", "--core", "--json")
        self.assertIn("setup --core", result.stderr)
        self.assertEqual(self.trace_text(), "")

    def test_selected_dataset_syntax_and_conflicts_stop_before_installer(self):
        for args in (("setup", "--dataset"), ("setup", "--dataset=../cvdp"),
                     ("setup", "--dataset", "x;touch bad"), ("doctor", "--dataset="),
                     ("setup", "--core", "--dataset", "cvdp"),
                     ("doctor", "--dataset=cvdp", "--core")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("--dataset" if "--core" not in args else "--core cannot", result.stderr)
                self.assertEqual(self.trace_text(), "")
        self.assertFalse((self.root / "external").exists())

    def test_selected_setup_syncs_core_without_docker_and_forwards_exact_name(self):
        self.tool("git")
        self.tool("docker", 'printf docker >> "$TRACE"; exit 99\n')
        self.uv()
        result = self.invoke("setup", "--dataset=verilog-spec", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("arg:sync\narg:--frozen", self.trace_text())
        self.assertIn("arg:setup\narg:--dataset=verilog-spec\narg:--offline", self.trace_text())
        self.assertNotIn("docker", self.trace_text())

    def test_selected_sync_failure_remedy_preserves_validated_dataset_scope(self):
        self.tool("git")
        self.tool("docker", 'printf docker >> "$TRACE"; exit 99\n')
        self.tool("uv", "exit 7\n")
        self.environment["HTTPS_PROXY"] = "http://SECRET@proxy.invalid"
        for options, name in ((("--dataset", "verilog-spec"), "verilog-spec"),
                              (("--dataset=cvdp", "--offline"), "cvdp")):
            with self.subTest(options=options):
                result = self.invoke("setup", *options)
                self.assertEqual(result.returncode, 2)
                self.assertIn("project-uv.log", result.stderr)
                self.assertIn(f"sh scripts/bootstrap.sh setup --dataset {name}", result.stderr)
                if "--offline" in options:
                    self.assertIn(f"setup --dataset {name} --offline", result.stderr)
                self.assertNotIn("SECRET", result.stdout + result.stderr)
                self.assertEqual(self.trace_text(), "")

    def test_make_selected_options_reach_python_unchanged(self):
        self.write_executable(self.root / ".venv/bin/python", '''
case "$1" in -I) exit 0;; esac
printf 'arg:%s\\n' "$@" >> "$TRACE"
printf '{"scope":"dataset","ready":false}\\n'
exit 2
''')
        result = self.invoke("doctor", "ARGS=--dataset verilog-spec --json", make=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["scope"], "dataset")
        self.assertIn("arg:--dataset\narg:verilog-spec\narg:--json", self.trace_text())

    def test_missing_prerequisites_aggregate_actionable_git_and_docker_guidance(self):
        result = self.invoke("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git", result.stderr)
        self.assertIn("Docker", result.stderr)
        self.assertIn("https://", result.stderr)
        self.assertIn("apt", result.stderr)
        self.assertEqual(self.trace_text(), "")

    def test_daemon_and_compose_failure_both_reported_before_install(self):
        self.tool("git")
        self.tool("docker", "exit 1\n")
        result = self.invoke("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("daemon", result.stderr)
        self.assertIn("Compose", result.stderr)
        self.assertIn("https://", result.stderr)
        self.assertEqual(self.trace_text(), "")

    def fast_deadline(self, seconds=0.2):
        (self.bin / "sleep").unlink()
        self.tool("sleep", f'case "$1" in 15) exec /bin/sleep {seconds};; *) exec /bin/sleep "$@";; esac\n')

    def test_stalled_short_probes_are_bounded_and_children_cleaned_without_touching_sentinel(self):
        self.fast_deadline()
        sentinel = subprocess.Popen(["/bin/sleep", "30"])
        self.addCleanup(sentinel.wait)
        self.addCleanup(sentinel.terminate)
        for target in ("git", "daemon", "compose", "project-python", "system-python", "setup-python"):
            with self.subTest(target=target):
                self.prerequisites()
                self.uv()
                python = self.root / ".venv/bin/python"
                if python.exists():
                    python.unlink()
                system = self.bin / "python3"
                if system.exists():
                    system.unlink()
                marker = self.outside / (target + "-leaked")
                stalled = (f'trap "" TERM INT\nprintf SECRET >&2\n'
                           f'(/bin/sleep 2; printf leaked > "{marker}") &\nwait\n')
                if target == "git":
                    self.tool("git", stalled)
                elif target in {"daemon", "compose"}:
                    argument = "info" if target == "daemon" else "compose"
                    self.tool("docker", f'if [ "$1" = {argument} ]; then\n{stalled}fi\nexit 1\n')
                elif target == "system-python":
                    self.tool("python3", stalled)
                else:
                    self.write_executable(python, stalled)
                command = "doctor" if target in {"project-python", "system-python"} else "setup"
                started = time.monotonic()
                result = self.invoke(command)
                self.assertLess(time.monotonic() - started, 1.8, result.stderr)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("timed out", result.stderr)
                self.assertIn("setup", result.stderr)
                self.assertNotIn("SECRET", result.stdout + result.stderr)
                self.assertIsNone(sentinel.poll())
        # A surviving descendant would write its marker even after the parent exits.
        time.sleep(2.1)
        self.assertEqual(list(self.outside.glob("*-leaked")), [])

    def test_slow_sync_is_not_subject_to_short_probe_deadline(self):
        # Allow normal interpreter startup under load, while sync still exceeds
        # the controlled probe deadline. This tests scoping, not host speed.
        self.fast_deadline(seconds=1)
        self.prerequisites()
        template = (self.outside / "uv-template").read_text()
        self.tool("uv", "/bin/sleep 1.2\n" + template)
        result = self.invoke("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("python:", self.trace_text())
        self.assertNotIn("timed out", result.stderr)

    def test_stalled_host_os_probe_has_prerequisite_deadline(self):
        self.fast_deadline()
        self.prerequisites()
        (self.bin / "uname").unlink()
        self.tool("uname", "/bin/sleep 2\nprintf Darwin\n")
        started = time.monotonic()
        result = self.invoke("setup", "--offline")
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prerequisites", result.stderr)
        self.assertIn("timed out", result.stderr)

    def test_offline_missing_uv_never_invokes_downloader(self):
        self.prerequisites()
        self.tool("curl", 'printf network >> "$TRACE"; exit 1\n')
        result = self.invoke("setup", "--offline")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uv", result.stderr)
        self.assertIn("offline", result.stderr.lower())
        self.assertEqual(self.trace_text(), "")

    def downloader(self, code):
        self.tool("curl", f'''
printf 'download:%s\\n' "$*" >> "$TRACE"
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then shift; cp "$INSTALLER" "$1"; break; fi
    shift
done
exit {code}
''')

    def test_failed_download_is_not_executed(self):
        self.prerequisites()
        self.downloader(22)
        result = self.invoke("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("download", result.stderr.lower())
        self.assertNotIn("installer:", self.trace_text())
        self.assertNotIn("uv:", self.trace_text())

    def test_installed_uv_prepares_python_without_system_python_and_keeps_environment(self):
        self.prerequisites()
        self.downloader(0)
        result = self.invoke("setup", "--platform", "linux/arm64")
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace_text()
        self.assertIn("https://astral.sh/uv/0.10.7/install.sh", trace)
        self.assertIn(f"installer:{self.root}/.cache/uv/bin:1", trace)
        self.assertIn(f"uv:{self.root}/.venv:", trace)
        self.assertIn("arg:--frozen", trace)
        self.assertIn("arg:3.12", trace)
        self.assertIn(f"python:{self.root}/.venv/bin/python:preserved value:{self.root}", trace)
        self.assertIn("arg:linux/arm64", trace)
        # A later command finds the repo-local uv without reinstalling anything.
        self.trace.write_text("")
        result = self.invoke("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("installer:", self.trace_text())

    def test_offline_sync_reaches_uv_with_no_python_downloads(self):
        self.prerequisites()
        self.uv()
        self.write_executable(self.root / ".venv/bin/python", '/bin/sleep 0.05\nexit 0\n')
        result = self.invoke("setup", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", "Successful probe cleanup must not print shell job diagnostics")
        self.assertIn("arg:--offline", self.trace_text())
        self.assertIn(f"uv:{self.root}/.venv:never", self.trace_text())

    def test_bootstrap_network_reaches_download_installer_and_sync_without_python(self):
        self.prerequisites()
        bundle = self.outside / "trust bundle.pem"
        bundle.write_text("fixture: downloader and uv are replaced")
        self.environment.update(AGENT_OPT_CA_BUNDLE=str(bundle), HTTP_PROXY="ignored",
                                http_proxy="", HTTPS_PROXY="http://user:secret@proxy",
                                NO_PROXY="localhost,.example.test")
        check = '''
[ "${HTTP_PROXY-unset}" = "" ]
[ "$https_proxy" = "$HTTPS_PROXY" ]
[ "$no_proxy" = "$NO_PROXY" ]
[ "$SSL_CERT_FILE" = "$AGENT_OPT_CA_BUNDLE" ]
[ "$CURL_CA_BUNDLE" = "$AGENT_OPT_CA_BUNDLE" ]
'''
        self.tool("curl", check + '''
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then shift; cp "$INSTALLER" "$1"; break; fi
    shift
done
''')
        for name in ("installer", "uv-template"):
            path = self.outside / name
            self.write_executable(path, check + path.read_text())
        result = self.invoke("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uv:", self.trace_text())
        self.assertNotIn("secret", result.stdout + result.stderr)

    def test_wget_bootstrap_uses_ca_for_installer_and_archive_then_cleans_config(self):
        self.prerequisites()
        bundle = self.outside / "trust bundle.pem"
        bundle.write_text("fixture")
        config = self.outside / "original-wgetrc"
        config.write_text("timeout = 30\n")
        self.environment.update(AGENT_OPT_CA_BUNDLE=str(bundle), WGETRC=str(config))
        check = '''
[ "$WGETRC" != "$HOME/original-wgetrc" ]
contents=$(cat "$WGETRC")
case "$contents" in *"timeout = 30"*"ca_certificate = $AGENT_OPT_CA_BUNDLE"*) ;; *) exit 9;; esac
printf 'wgetrc:%s\\n' "$WGETRC" >> "$TRACE"
'''
        (self.bin / "cat").symlink_to(shutil.which("cat"))
        self.tool("wget", check + '''
while [ "$#" -gt 0 ]; do
    if [ "$1" = -O ]; then shift; cp "$INSTALLER" "$1"; break; fi
    shift
done
''')
        installer = self.outside / "installer"
        self.write_executable(installer, check + installer.read_text())
        result = self.invoke("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_text(), "timeout = 30\n")
        paths = [line.partition(":")[2] for line in self.trace_text().splitlines() if line.startswith("wgetrc:")]
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(not Path(path).exists() for path in paths))

    def test_readonly_commands_do_not_install_and_invalid_options_cannot_execute_shell(self):
        self.tool("curl", 'printf network >> "$TRACE"\n')
        self.uv()
        for command in ("doctor", "test", "lint", "demo", "smoke", "live"):
            result = self.invoke(command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("setup", result.stderr)
        for args in (("setup", "--json"), ("smoke", "--offline"),
                     ("demo", "--platform", "linux/amd64"),
                     ("setup", "--platform", "linux/amd64; touch injected")):
            result = self.invoke(*args)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.outside / "injected").exists())
        self.assertEqual(self.trace_text(), "")

    def test_make_options_are_normal_quoted_arguments_and_json_stdout_is_clean(self):
        self.write_executable(self.root / ".venv/bin/python", '''
case "$1" in -I) exit 0;; esac
printf 'arg:%s\\n' "$@" >> "$TRACE"
printf '{"ready":false}\\n'
exit 2
''')
        result = self.invoke("doctor", 'ARGS=--json --platform "linux/arm64"', make=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout.strip(), result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ready": False})
        self.assertIn("arg:--json\narg:--platform\narg:linux/arm64\n", self.trace_text())

    def test_venv_symlink_identity_and_sentinel_survive_setup(self):
        venv.EnvBuilder(with_pip=False, symlinks=True).create(self.root / ".venv")
        sentinel = self.root / ".venv/keep"
        sentinel.write_text("user-owned")
        (self.root / "scripts/dev.py").write_text(
            "import sys; print(sys.prefix); assert sys.prefix != sys.base_prefix\n")
        self.prerequisites()
        self.uv()
        result = self.invoke("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.root / ".venv"), result.stdout)
        self.assertEqual(sentinel.read_text(), "user-owned")
        self.assertTrue((self.root / ".venv/bin/python").is_symlink())
        self.assertIn(f"arg:{self.root}/.venv/bin/python", self.trace_text())

    def test_readonly_falls_back_to_compatible_system_python_without_installing(self):
        self.tool("python3", '''
case "$1" in -I) exit 0;; esac
printf 'system-python\\n'
''')
        result = self.invoke("doctor", "--json", "--platform", "untrusted; touch injected")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "system-python\n")
        self.assertFalse((self.outside / "injected").exists())
        self.assertFalse((self.root / ".venv").exists())

    def test_sync_failure_stops_before_python_dispatch_with_log_and_repair(self):
        self.prerequisites()
        self.tool("uv", "exit 7\n")
        result = self.invoke("setup", "--offline")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("project-uv.log", result.stderr)
        self.assertIn("rerun", result.stderr)
        self.assertNotIn("python:", self.trace_text())

    def test_existing_broken_environment_is_preserved_without_uv_sync(self):
        self.prerequisites()
        self.uv()
        sentinel = self.root / ".venv/keep"
        sentinel.parent.mkdir()
        sentinel.write_text("user-owned")
        result = self.invoke("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preserved", result.stderr)
        self.assertEqual(sentinel.read_text(), "user-owned")
        self.assertEqual(self.trace_text(), "")

    def test_installer_failure_or_no_executable_stops_and_cleans_temporary_file(self):
        self.prerequisites()
        self.downloader(0)
        temporary = self.outside / "installer-temp"
        temporary.mkdir()
        self.environment["TMPDIR"] = str(temporary)
        for code in (7, 0):
            with self.subTest(installer_exit=code):
                self.trace.write_text("")
                self.write_executable(self.outside / "installer", f"exit {code}\n")
                result = self.invoke("setup")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("bootstrap-uv.log", result.stderr)
                self.assertIn("rerun", result.stderr)
                self.assertNotIn("uv:", self.trace_text())
                self.assertNotIn("python:", self.trace_text())
                self.assertEqual(list(temporary.iterdir()), [])

    def test_filesystem_failures_name_stage_path_and_repair_before_later_work(self):
        self.prerequisites()
        self.downloader(0)
        for failure in ("log-directory", "temporary-file"):
            with self.subTest(failure=failure):
                self.trace.write_text("")
                if failure == "log-directory":
                    external = self.root / "external"
                    external.write_text("preserve")
                    path = str(external / "setup-logs")
                else:
                    external.unlink()
                    path = str(self.outside / "missing-temp")
                    self.environment["TMPDIR"] = path
                result = self.invoke("setup")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("uv preparation", result.stderr)
                self.assertIn(path, result.stderr)
                self.assertIn("rerun", result.stderr)
                self.assertEqual(self.trace_text(), "")

    def test_sync_without_python_reports_dispatch_stage_and_repair(self):
        self.prerequisites()
        self.tool("uv")
        result = self.invoke("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dispatch", result.stderr)
        self.assertIn(str(self.root / ".venv/bin/python"), result.stderr)
        self.assertIn("rerun", result.stderr)


class DeveloperCommandsTests(unittest.TestCase):
    def setUp(self):
        self.dev = module("dev_onboarding", ROOT / "scripts/dev.py")
        self.output = io.StringIO()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}).start()
        patch.object(self.dev.os, "chdir").start()

    def main(self, args):
        with redirect_stdout(self.output), redirect_stderr(self.output):
            return self.dev.main(args)

    def test_no_arguments_means_help(self):
        self.assertEqual(self.main([]), 0)
        self.assertIn("사용법:", self.output.getvalue())
        self.assertIn("옵션:", self.output.getvalue())
        self.assertIn("demo", self.output.getvalue())

    def test_doctor_json_keeps_stdout_separate_from_running_status(self):
        report = {"scope": "core", "ready": True, "areas": {"core": True}, "checks": []}
        doctor = SimpleNamespace(collect_report=lambda *args, **kwargs: report,
                                 render_report=lambda row, json_output=False: print(json.dumps(row)))
        output, progress = io.StringIO(), io.StringIO()
        with patch.object(self.dev, "load", return_value=doctor), \
                redirect_stdout(output), redirect_stderr(progress):
            self.assertEqual(self.dev.main(["doctor", "--core", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue()), report)
        self.assertIn("[doctor] check=environment starting", progress.getvalue())
        self.assertIn("[doctor] check=environment complete", progress.getvalue())

    def test_direct_core_doctor_progress_does_not_require_rich_before_setup(self):
        result = subprocess.run([str(ROOT / ".venv/bin/python"), "-S", "scripts/dev.py", "doctor", "--core", "--json"],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ready"])
        self.assertIn("[doctor] check=environment starting", result.stderr)

    def test_network_is_loaded_before_core_and_shell_setup(self):
        def inspect(*args, **kwargs):
            self.assertEqual(os.environ.get("https_proxy"), "http://user:secret@proxy")
            return {"ready": True}
        doctor = SimpleNamespace(collect_report=inspect, render_report=lambda *a, **k: None)
        for command in ("test", "setup"):
            with self.subTest(command=command), patch.dict(
                    os.environ, {"HTTPS_PROXY": "http://user:secret@proxy"}, clear=True), \
                    patch.object(self.dev, "load", return_value=doctor), \
                    patch.object(self.dev, "run_core", side_effect=lambda *a: inspect() and 0), \
                    patch("subprocess.run", side_effect=lambda *a, **k: inspect() and subprocess.CompletedProcess([], 0)):
                self.assertEqual(self.main([command]), 0)
        self.assertNotIn("secret", self.output.getvalue())

    def test_invalid_ca_setup_and_runtime_remain_fail_closed(self):
        with patch.dict(os.environ, {"AGENT_OPT_CA_BUNDLE": "/missing-SECRET.pem"}, clear=True), \
                patch.object(self.dev, "load", side_effect=AssertionError("must fail before execution")), \
                patch("subprocess.run", side_effect=AssertionError("must fail before execution")):
            for command in ("setup", "smoke", "live"):
                with self.subTest(command=command):
                    self.output = io.StringIO()
                    self.assertEqual(self.main([command]), 2)
                    self.assertIn("AGENT_OPT_CA_BUNDLE", self.output.getvalue())
                    self.assertNotIn("SECRET", self.output.getvalue())

    def test_rejects_unsupported_options_before_any_external_operation(self):
        with patch.object(self.dev, "load", side_effect=AssertionError("loaded external code")):
            for args in (("smoke", "--offline"), ("live", "--offline"), ("setup", "--json"),
                         ("test", "--platform", "linux/amd64"), ("help", "--offline")):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    self.main(args)
                    self.fail("unsupported options were accepted")

    def test_core_commands_use_actual_project_venv_and_propagate_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            venv.EnvBuilder(with_pip=False, symlinks=True).create(root / ".venv")
            # Real interpreter/prefix check, external command only is replaced.
            original = subprocess.run
            commands = []
            def execute(argv, **kwargs):
                if "-c" in argv:
                    return original(argv, **kwargs)
                commands.append((argv, kwargs))
                return subprocess.CompletedProcess(argv, 7)
            with patch.object(self.dev, "ROOT", root), patch("subprocess.run", side_effect=execute):
                for command in ("test", "lint", "demo"):
                    self.assertEqual(self.main([command]), 7)
            self.assertEqual([c[0][0] for c in commands], [str(root / ".venv/bin/python")] * 3)
            self.assertEqual([c[0][2] for c in commands], ["unittest", "ruff", "agent_optimizer"])
            self.assertTrue(all(c[1]["cwd"] == root for c in commands))
            self.assertTrue(all(c[1]["shell"] is False for c in commands))

    def test_missing_or_nonvenv_python_has_actionable_setup_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for exists in (False, True):
                if exists:
                    (root / ".venv/bin").mkdir(parents=True)
                    (root / ".venv/bin/python").symlink_to(sys.executable)
                with patch.object(self.dev, "ROOT", root):
                    self.assertEqual(self.main(["test"]), 2)
                self.assertIn("setup --core", self.output.getvalue())

    def test_missing_dev_dependency_reports_setup_remedy_without_installing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            venv.EnvBuilder(with_pip=False, symlinks=True).create(root / ".venv")
            with patch.object(self.dev, "ROOT", root):
                self.assertNotEqual(self.main(["lint"]), 0)
            self.assertIn("setup --core", self.output.getvalue())

    def test_core_options_reject_conflicts_before_loading(self):
        with patch.object(self.dev, "load", side_effect=AssertionError("external loader")):
            for args in (("setup", "--core", "--platform", "linux/amd64"),
                         ("doctor", "--core", "--model"),
                         ("doctor", "--platform=linux/arm64", "--core")):
                self.output = io.StringIO()
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    self.main(args)
                self.assertIn("--core cannot", self.output.getvalue())
            for command in ("test", "lint", "demo", "smoke", "live", "menu"):
                with self.subTest(command=command), self.assertRaises(SystemExit):
                    self.main([command, "--core"])

    def test_setup_and_doctor_help_explain_dataset_scope_and_legal_flags(self):
        for command in ("setup", "doctor"):
            self.output = io.StringIO()
            with self.subTest(command=command), self.assertRaises(SystemExit) as exit_code:
                self.main([command, "--help"])
            self.assertEqual(exit_code.exception.code, 0)
            help_text = self.output.getvalue()
            self.assertIn("ACE 전체", help_text)
            self.assertIn("--dataset ID", help_text)
            self.assertIn("--core/--platform/--model", help_text)
            if command == "doctor":
                self.assertIn("등록 데이터셋 하나 진단", help_text)
                self.assertIn("--model", help_text)
            else:
                self.assertIn("등록 데이터셋 하나 준비", help_text)

    def test_core_setup_stops_before_example_and_requires_doctor_then_demo(self):
        for ready, demo_code, expected in ((True, 0, 0), (False, 0, 2), (True, 5, 2)):
            events = []
            def report(root, platform=None, *, core_only=False):
                self.assertTrue(core_only)
                events.append("doctor")
                return {"ready": ready, "scope": "core", "areas": {"core": ready}, "checks": []}
            doctor = SimpleNamespace(collect_report=report, render_report=lambda *a, **k: None)
            def load(name, path):
                self.assertEqual(name, "dev_doctor", "core setup loaded example code")
                return doctor
            def execute(command):
                events.append(command)
                return demo_code
            self.output = io.StringIO()
            with self.subTest(ready=ready, demo_code=demo_code), \
                    patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                    patch.object(self.dev, "load", side_effect=load), \
                    patch.object(self.dev, "run_core", side_effect=execute):
                self.assertEqual(self.main(["setup", "--core", "--offline"]), expected)
            self.assertEqual(events, ["doctor", "demo"] if ready else ["doctor"])
            result = json.loads(self.output.getvalue().splitlines()[-1])
            self.assertEqual(result["status"], "ready" if expected == 0 else "blocked")
            if expected == 0:
                self.assertEqual(result["scope"], "core")
                self.assertNotIn("environment_lock", result)
            else:
                self.assertIn("setup --core", result["repair"])

    def test_direct_python_setup_delegates_without_recursion_and_propagates_failure(self):
        with patch.dict(os.environ, {}, clear=True), patch("subprocess.run", return_value=subprocess.CompletedProcess([], 9)) as run:
            self.assertEqual(self.main(["setup", "--offline", "--platform", "linux/amd64"]), 9)
        self.assertEqual(run.call_args.args[0], ["sh", str(ROOT / "scripts/bootstrap.sh"), "setup",
                                               "--offline", "--platform", "linux/amd64"])

    def test_selected_setup_resolves_after_sync_and_requires_shared_doctor(self):
        from agent_optimizer.registry import Registry
        from agent_optimizer import readiness
        doctor = module("onboarding_selected_doctor", ROOT / "scripts/dev_doctor.py")
        events = []
        class Provider:
            def prepare(self, cache, *, offline=False):
                events.append(("prepare", cache, offline))
                return {"benchmark": "fixture", "evaluator": "fixture", "provenance": {}}
        def load_project(registry, root):
            events.append(("registry", root))
            registry.factories["datasets"]["sample_text"] = Provider
            registry.factories["evaluators"]["fixture"] = object
        def collect(root, name, registry):
            events.append(("doctor", name))
            return {"scope": "dataset", "ready": self.ready, "checks": []}
        for self.ready in (True, False):
            events.clear()
            self.output = io.StringIO()
            progress = io.StringIO()
            with patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                    patch.object(Registry, "load_project", load_project), \
                    patch.object(readiness, "collect_dataset", collect), \
                    patch.object(doctor, "core_checks", return_value=[]), \
                    patch.object(self.dev, "load", side_effect=lambda name, path: doctor if name == "dev_doctor" else self.fail("ACE path loaded")), \
                    patch.object(self.dev, "run_core", side_effect=AssertionError("demo run")), \
                    redirect_stdout(self.output), redirect_stderr(progress):
                self.assertEqual(self.dev.main(["setup", "--dataset", "sample_text", "--offline"]),
                                 0 if self.ready else 2)
            self.assertEqual(events, [("registry", ROOT),
                                      ("prepare", ROOT / "external/datasets/sample_text", True),
                                      ("doctor", "sample_text")])
            self.assertEqual('"status": "ready"' in self.output.getvalue(), self.ready)
            self.assertIn("[setup] dataset=sample_text starting", progress.getvalue())
            self.assertIn("[doctor] check=dataset starting", progress.getvalue())

    def test_selected_setup_rejects_provider_evaluator_file_reference_before_ready(self):
        from agent_optimizer.registry import Registry
        class Provider:
            def prepare(self, cache, *, offline=False):
                return {"benchmark": "fixture", "evaluator": "examples/minimal/evaluator.py:TextFixtureEvaluator",
                        "provenance": {}}
        with patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                patch.object(Registry, "load_project", lambda registry, root:
                             registry.factories["datasets"].update(sample_text=Provider)), \
                patch.object(self.dev, "load", side_effect=AssertionError("doctor must not run")):
            self.assertEqual(self.main(["setup", "--dataset", "sample_text"]), 2)
        self.assertIn("registered evaluator ID", self.output.getvalue())
        self.assertNotIn('"status": "ready"', self.output.getvalue())

    def test_selected_setup_rejects_unregistered_evaluator_id_despite_ready_doctor(self):
        from agent_optimizer.registry import Registry
        class Provider:
            def prepare(self, cache, *, offline=False):
                return {"benchmark": "fixture", "evaluator": "missing_eval", "provenance": {}}
        doctor = SimpleNamespace(collect_report=lambda *a, **kw: {"ready": True},
                                 render_report=lambda *a, **kw: None)
        with patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                patch.object(Registry, "load_project", lambda registry, root:
                             registry.factories["datasets"].update(sample_text=Provider)), \
                patch.object(self.dev, "load", return_value=doctor):
            self.assertEqual(self.main(["setup", "--dataset", "sample_text"]), 2)
        self.assertIn("missing_eval", self.output.getvalue())
        self.assertIn("src/agent_optimizer/registry.py", self.output.getvalue())
        self.assertNotIn('"status": "ready"', self.output.getvalue())

    def test_unknown_selected_name_fails_after_core_sync_before_provider(self):
        from agent_optimizer.registry import Registry
        events = []
        with patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                patch.object(Registry, "load_project", lambda registry, root: events.append("registry")), \
                patch.object(self.dev, "load", side_effect=AssertionError("ACE path loaded")):
            self.assertEqual(self.main(["setup", "--dataset", "absent"]), 2)
        self.assertEqual(events, ["registry"])
        self.assertIn("absent", self.output.getvalue())
        self.assertIn("agent-opt datasets list", self.output.getvalue())

    def test_python_selected_dataset_conflicts_and_bad_names_before_dispatch(self):
        with patch.object(self.dev, "load", side_effect=AssertionError("loader")), \
                patch("subprocess.run", side_effect=AssertionError("installer")):
            for args in (("setup", "--core", "--dataset", "cvdp"),
                         ("doctor", "--dataset", "cvdp", "--core"),
                         ("setup", "--dataset", "../cvdp"),
                         ("doctor", "--dataset", "bad;id")):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    self.main(args)

    def test_direct_python_doctor_finds_bootstrap_local_uv_without_shell_profile_changes(self):
        doctor = module("onboarding_local_uv", ROOT / "scripts/dev_doctor.py")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            uv = root / ".cache/uv/bin/uv"
            uv.parent.mkdir(parents=True)
            uv.write_text("#!/bin/sh\nprintf 'uv 0.10.7\\n'\n")
            uv.chmod(0o755)
            output, progress = io.StringIO(), io.StringIO()
            with patch.object(self.dev, "ROOT", root), patch.object(self.dev, "load", return_value=doctor), \
                    patch.dict(os.environ, {"PATH": str(root / "missing")}, clear=True), \
                    redirect_stdout(output), redirect_stderr(progress):
                self.assertEqual(self.dev.main(["doctor", "--json"]), 2)
            checks = {c["id"]: c for c in json.loads(output.getvalue())["checks"]}
            self.assertEqual(checks["core.uv"]["status"], "ok")
            self.assertIn("[doctor] check=environment starting", progress.getvalue())
            self.assertFalse((root / ".venv").exists())

    def setup_flow(self, failure=None, ready=True, demo_code=0):
        events = []
        def environment(**kwargs):
            events.append("environment")
            self.assertTrue(kwargs["offline"])
            if failure:
                raise failure
            return ROOT / "dataset", {}
        setup = SimpleNamespace(validate_platform=lambda value: value, prepare_environment=environment)
        def dataset(*args):
            events.append("dataset")
            return {"tasks": [{"id": "cvdp_copilot_16qam_mapper_0001", "family": "qam"},
                              {"id": "cvdp_copilot_8x3_priority_encoder_0001", "family": "priority"}]}
        def report(*args):
            events.append("doctor")
            return {"ready": ready}
        doctor = SimpleNamespace(collect_report=report, render_report=lambda *a, **kw: None)
        def execute(command):
            events.append(command)
            return demo_code
        with patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(ROOT)}), \
                patch.object(self.dev, "load", side_effect=[setup, SimpleNamespace(prepare_dataset=dataset),
                    module("onboarding_demo_selector", ROOT / "examples/ace-rtl/environment/demo.py"), doctor]), \
                patch.object(self.dev, "write_json"), \
                patch.object(self.dev, "run_core", side_effect=execute, create=True):
            code = self.main(["setup", "--offline", "--platform", "linux/amd64"])
        return code, events

    def test_setup_stages_finish_only_after_final_doctor_and_demo(self):
        code, events = self.setup_flow()
        self.assertEqual(code, 0)
        self.assertEqual(events, ["environment", "dataset", "doctor", "demo"])
        self.assertIn("setup-logs", self.output.getvalue())
        self.assertIn("ready", self.output.getvalue())

    def test_setup_failure_and_interrupt_halt_with_stage_repair_and_no_ready(self):
        for failure in (UnavailableError("source mismatch"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure)):
                self.output = io.StringIO()
                try:
                    code, events = self.setup_flow(failure=failure)
                except KeyboardInterrupt:
                    self.fail("setup did not handle interruption with stage diagnostics")
                self.assertNotEqual(code, 0)
                self.assertEqual(events, ["environment"])
                self.assertIn("setup", self.output.getvalue())
                self.assertIn("setup-logs", self.output.getvalue())
                self.assertNotIn('"status": "ready"', self.output.getvalue())

    def test_final_doctor_and_demo_failure_cannot_report_ready(self):
        for ready, demo_code, expected in ((False, 0, ["environment", "dataset", "doctor"]),
                                           (True, 5, ["environment", "dataset", "doctor", "demo"])):
            self.output = io.StringIO()
            code, events = self.setup_flow(ready=ready, demo_code=demo_code)
            self.assertNotEqual(code, 0)
            self.assertEqual(events, expected)
            self.assertNotIn('"status": "ready"', self.output.getvalue())

    def test_live_auth_is_checked_before_docker_or_prepared_assets(self):
        setup = module("onboarding_auth", ROOT / "examples/ace-rtl/environment/setup.py")
        with patch.dict(os.environ, {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/chat/completion"}, clear=True), patch.object(self.dev, "load", return_value=setup), \
                patch.object(setup, "validate_platform", side_effect=AssertionError("Docker before auth")):
            self.assertEqual(self.main(["live"]), 2)
        self.assertIn("blocked_auth", self.output.getvalue())

    def test_corrupted_lock_is_preserved_and_reported_before_later_setup_smoke_live_stages(self):
        setup = module("onboarding_corrupt_lock", ROOT / "examples/ace-rtl/environment/setup.py")
        valid = {"platform": "linux/amd64", "images": {
            "evaluation": {"tag": "eval", "id": "sha256:eval"},
            "agent": {"tag": "agent", "id": "sha256:agent"},
        }}
        malformed = ["{truncated", "[]", "null", "{}", '{"images": []}',
                     json.dumps({**valid, "images": {"evaluation": []}}),
                     json.dumps({**valid, "driver_packages": []}),
                     json.dumps({**valid, "driver_requirements": []})]
        for command in ("setup", "smoke", "live"):
            for offline in ((False, True) if command == "setup" else (False,)):
                for contents in malformed:
                    with self.subTest(command=command, offline=offline, contents=contents), tempfile.TemporaryDirectory() as d:
                        root = Path(d)
                        lock = root / "external/environment-lock.json"
                        lock.parent.mkdir()
                        lock.write_text(contents)
                        self.output = io.StringIO()
                        with patch.object(self.dev, "ROOT", root), patch.object(setup, "ROOT", root), \
                                patch.object(self.dev, "load", side_effect=[setup]), \
                                patch.object(setup, "prepare_sources"), \
                                patch.object(setup, "driver_requirements", return_value={}), \
                                patch.object(setup, "prepare_data", side_effect=AssertionError("later data work")), \
                                patch.dict(os.environ, {"AGENT_OPT_BOOTSTRAPPED": str(root),
                                            "AGENT_OPT_MODEL_API_KEY": "test", "AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/chat/completion"}):
                            code = self.main([command, "--platform", "linux/amd64", *(["--offline"] if offline else [])])
                        self.assertEqual(code, 2)
                        blocked = json.loads(self.output.getvalue().splitlines()[-1])
                        self.assertEqual(blocked["status"], "blocked")
                        self.assertEqual(blocked["stage"], "example environment" if command == "setup" else command)
                        self.assertIn(str(lock), blocked["reason"])
                        self.assertIn("preserved", blocked["reason"])
                        self.assertIn("setup", blocked["repair"])
                        self.assertNotIn("Traceback", self.output.getvalue())
                        self.assertNotIn('"status": "ready"', self.output.getvalue())
                        self.assertEqual(lock.read_text(), contents)

    def test_unexpected_implementation_error_is_not_swallowed_as_persisted_state_error(self):
        with self.assertRaisesRegex(RuntimeError, "implementation defect"):
            self.setup_flow(failure=RuntimeError("implementation defect"))


class PreparationProgressTests(unittest.TestCase):
    def test_long_command_announces_log_and_only_marks_success_after_exit_zero(self):
        setup = module("onboarding_progress", ROOT / "examples/ace-rtl/environment/setup.py")
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "driver-uv.log"
            for code in (0, 6):
                output = io.StringIO()
                def execute(*args, **kwargs):
                    self.assertIn(str(log), output.getvalue(), "log path must precede slow command")
                    return subprocess.CompletedProcess([], code)
                with redirect_stdout(output), patch.object(setup.subprocess, "run", side_effect=execute):
                    if code:
                        with self.assertRaisesRegex(UnavailableError, "driver-uv.log"):
                            setup.run(["uv", "pip", "sync"], log=log)
                    else:
                        setup.run(["uv", "pip", "sync"], log=log)
                self.assertEqual("complete" in output.getvalue(), code == 0)
