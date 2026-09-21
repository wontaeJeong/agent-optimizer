import importlib
import importlib.util
import copy
import json
import os
import ssl
import subprocess
import sys
import tempfile
import unittest
import hashlib
import threading
import uuid
import io
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError, ExecutionResult
from agent_optimizer.process import execute


def network_module(test):
    from agent_optimizer import process
    test.assertTrue(hasattr(process, "host_environment"), "network contract not connected")
    return importlib.import_module("agent_optimizer.network")


def certificate(directory):
    cert = Path(directory) / "ca.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(Path(directory) / "key.pem"), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=localhost"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return cert


class NetworkTests(unittest.TestCase):
    def test_cli_applies_network_to_in_process_plugins(self):
        from agent_optimizer import cli
        captured = {}
        def inspect():
            captured.update(os.environ)
            return {}
        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy.test"}, clear=True), \
                patch.object(cli, "doctor", side_effect=inspect), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["doctor"]), 0)
        self.assertEqual(captured.get("http_proxy"), "http://proxy.test")

    def test_lowercase_precedence_empty_and_absent(self):
        network = network_module(self)
        self.assertEqual(network.network_environment({}), {})
        env = network.network_environment({"HTTP_PROXY": "ignored", "http_proxy": "",
                                           "NO_PROXY": "localhost,.example.test:443",
                                           "OPENAI_API_KEY": "not-network"})
        self.assertEqual(env, {"HTTP_PROXY": "", "http_proxy": "",
                               "NO_PROXY": "localhost,.example.test:443",
                               "no_proxy": "localhost,.example.test:443"})

    def test_ca_is_validated_and_overrides_tool_paths(self):
        network = network_module(self)
        with tempfile.TemporaryDirectory() as d:
            cert = certificate(d)
            env = network.host_environment({"AGENT_OPT_CA_BUNDLE": str(cert),
                                            "SSL_CERT_FILE": "/incorrect", "KEEP": "yes"})
            self.assertEqual(env["SSL_CERT_FILE"], str(cert))
            self.assertEqual(env["REQUESTS_CA_BUNDLE"], str(cert))
            self.assertEqual(env["NODE_EXTRA_CA_CERTS"], str(cert))
            self.assertEqual(env["KEEP"], "yes")
            self.assertTrue(ssl.create_default_context(cafile=env["SSL_CERT_FILE"]).get_ca_certs())
            for bad in (str(Path(d) / "missing"), d):
                with self.assertRaises(ConfigurationError):
                    network.host_environment({"AGENT_OPT_CA_BUNDLE": bad})
            cert.write_text("not a PEM certificate")
            with self.assertRaises(ConfigurationError):
                network.host_environment({"AGENT_OPT_CA_BUNDLE": str(cert)})

    def test_local_child_receives_normalized_network_environment(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"HTTP_PROXY": "http://proxy.test:3128"}, clear=True):
            root = Path(d)
            result = execute([sys.executable, "-c", "import os,json; print(json.dumps(dict(os.environ)))"],
                             root, root / "logs", 5, {"kind": "local"})
            self.assertEqual(result.status, "completed")
            actual = json.loads(Path(result.stdout_path).read_text())
            self.assertEqual(actual.get("http_proxy"), "http://proxy.test:3128")

    def test_docker_uses_container_ca_paths_without_proxy_values_in_argv(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cert = certificate(d)
            environ = {"AGENT_OPT_CA_BUNDLE": str(cert), "HTTPS_PROXY": "http://user:secret@proxy:3128",
                       "NO_PROXY": "api.test,localhost", "MODEL_API_KEY": "do-not-forward"}
            with patch.dict(os.environ, environ, clear=True), \
                    patch("agent_optimizer.process.run_process", return_value=ExecutionResult("completed", 0, 0, "", "")) as run, \
                    patch("agent_optimizer.process.subprocess.run"):
                execute(["python3", "-V"], root, root / "logs", 5,
                        {"kind": "docker", "image": "example", "network": "none"})
            argv = run.call_args.args[0]
            self.assertIn("HTTPS_PROXY", argv)
            self.assertNotIn("secret", " ".join(argv))
            self.assertNotIn("MODEL_API_KEY", " ".join(argv))
            self.assertIn("SSL_CERT_FILE=/opt/agent-optimizer/ca-bundle.pem", argv)
            self.assertIn(f"type=bind,source={cert},target=/opt/agent-optimizer/ca-bundle.pem,readonly", argv)
            self.assertEqual(argv[argv.index("--network") + 1], "none")
            client = run.call_args.kwargs["env"]
            self.assertEqual(client["https_proxy"], "http://user:secret@proxy:3128")


class BuildNetworkTests(unittest.TestCase):
    def test_build_context_is_temporary_and_original_stays_unchanged(self):
        network = network_module(self)
        self.assertTrue(hasattr(network, "configured_build"), "CA-aware build missing")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cert = certificate(d)
            original = "FROM ubuntu:24.04\nRUN apt-get update\n"
            (root / "Dockerfile").write_text(original)
            args = ["docker", "build", "-f", "Dockerfile", "-t", "test", "."]
            env = {"AGENT_OPT_CA_BUNDLE": str(cert), "HTTPS_PROXY": "http://user:secret@proxy"}
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                with network.configured_build(args, root, env) as command:
                    self.assertNotIn("secret", " ".join(command))
                    generated = Path(command[command.index("-f") + 1])
                    recipe = generated.read_text()
                    self.assertLess(recipe.index("COPY"), recipe.index("RUN apt-get"))
                    self.assertIn("SSL_CERT_FILE=", recipe)
                    self.assertNotIn("HTTPS_PROXY", recipe)
                    context = Path(command[command.index("--build-context") + 1].split("=", 1)[1])
                    self.assertEqual([p.name for p in context.iterdir()], ["ca-bundle.pem"])
                    self.assertEqual((context / "ca-bundle.pem").read_bytes(), cert.read_bytes())
                    self.assertEqual((root / "Dockerfile").read_text(), original)
                    raise RuntimeError("build failed")
            self.assertFalse(generated.exists())
            self.assertFalse(context.exists())

    def test_unconfigured_build_does_not_need_buildkit_or_read_context(self):
        network = network_module(self)
        self.assertTrue(hasattr(network, "configured_build"), "CA-aware build missing")
        args = ["docker", "build", "-f", "Dockerfile", "-t", "test", "."]
        with network.configured_build(args, Path("/not-present"), {}) as command:
            self.assertEqual(command, args)

    def test_setup_build_and_host_command_use_the_same_environment(self):
        from test_dev_environment import setup
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Dockerfile").write_text("FROM ubuntu:24.04\nRUN true\n")
            cert = certificate(d)
            env = {"AGENT_OPT_CA_BUNDLE": str(cert), "HTTPS_PROXY": "http://proxy.test"}
            commands = []
            def run(argv, **kwargs):
                commands.append((argv, kwargs["env"]))
                return subprocess.CompletedProcess(argv, 0)
            with patch.dict(os.environ, env, clear=True), patch.object(setup.subprocess, "run", side_effect=run):
                setup.run(["uv", "sync"], cwd=root)
                setup.run(["docker", "build", "-f", "Dockerfile", "."], cwd=root)
            self.assertEqual(commands[0][1].get("REQUESTS_CA_BUNDLE"), str(cert))
            self.assertEqual(commands[0][1].get("https_proxy"), "http://proxy.test")
            self.assertIn("--build-context", commands[1][0])

    def test_offline_ca_change_rejected_before_setup_commands(self):
        from test_dev_environment import setup
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "external").mkdir()
            (root / "external/environment-lock.json").write_text(json.dumps({
                "ca_bundle_sha256": "old", "platform": "linux/arm64", "images": {
                    "evaluation": {"tag": "eval", "id": "sha256:eval"},
                    "agent": {"tag": "agent", "id": "sha256:agent"},
                }}))
            with patch.dict(os.environ, {}, clear=True), patch.object(setup, "ROOT", root), \
                    patch.object(setup, "run") as run:
                with self.assertRaisesRegex(ConfigurationError, "CA"):
                    setup.prepare_environment(offline=True, platform="linux/arm64")
                run.assert_not_called()


class LocalNetworkIntegrationTests(unittest.TestCase):
    def server(self, payload, tls=None):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        if tls:
            server.socket = tls.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def stop():
            server.shutdown()
            server.server_close()
            worker.join()
        self.addCleanup(stop)
        return server.server_port

    def test_dataset_download_accepts_configured_ca_and_rejects_untrusted_tls(self):
        from test_dev_environment import setup
        from agent_optimizer.contracts import UnavailableError
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cert = certificate(d)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cert, root / "key.pem")
            port = self.server(b"verified payload", tls)
            url = f"https://localhost:{port}/asset"
            digest = hashlib.sha256(b"verified payload").hexdigest()
            with patch.dict(os.environ, {"NO_PROXY": "localhost"}, clear=True):
                with self.assertRaises(UnavailableError):
                    setup.fetch_asset(url, root / "untrusted", digest)
            with patch.dict(os.environ, {"NO_PROXY": "localhost", "AGENT_OPT_CA_BUNDLE": str(cert)}, clear=True):
                setup.fetch_asset(url, root / "trusted", digest)
            self.assertEqual((root / "trusted").read_bytes(), b"verified payload")

    def test_real_child_routes_through_proxy_and_no_proxy_bypasses_it(self):
        origin = self.server(b"direct")
        proxy = self.server(b"proxied")
        code = ("import urllib.request; "
                f"print(urllib.request.urlopen('http://localhost:{origin}/', timeout=5).read().decode())")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for bypass, expected in (("", "proxied"), ("localhost", "direct")):
                env = {"HTTP_PROXY": f"http://127.0.0.1:{proxy}", "NO_PROXY": bypass}
                with patch.dict(os.environ, env, clear=True):
                    result = execute([sys.executable, "-c", code], root, root / expected, 10, {"kind": "local"})
                self.assertEqual(result.status, "completed")
                self.assertEqual(Path(result.stdout_path).read_text().strip(), expected)


class EvaluatorNetworkTests(unittest.TestCase):
    def test_network_settings_never_replace_owned_network_name(self):
        from test_dev_environment import cvdp, official_row, prepare
        from agent_optimizer.contracts import Task
        for env in ({}, {"HTTPS_PROXY": "http://user:secret@proxy"}):
            with self.subTest(configured=bool(env)), tempfile.TemporaryDirectory() as d:
                output = Path(d) / "output"
                (output / "rtl").mkdir(parents=True)
                (output / "rtl/dut.sv").write_text("module dut; endmodule")
                task = Task(**prepare.convert([official_row()])[0][0])
                with patch.dict(os.environ, env, clear=True), \
                        patch.object(cvdp, "run_process", return_value=ExecutionResult("process_error", 1, 0, "", "")) as run, \
                        patch.object(cvdp, "cleanup_network") as cleanup:
                    cvdp.CVDPEvaluator().evaluate(task, output, 5)
                argv = run.call_args.args[0]
                self.assertTrue(all(isinstance(arg, str) for arg in argv), "all subprocess arguments must be strings")
                name = argv[argv.index("--network-name") + 1]
                self.assertRegex(name, r"^agent-opt-cvdp-[0-9a-f]{32}$")
                self.assertEqual(cleanup.call_args.args[0], name)
                self.assertNotIn("secret", " ".join(argv))

    def driver(self):
        path = Path(__file__).resolve().parents[1] / "examples/ace-rtl/environment/network_driver.py"
        self.assertTrue(path.is_file(), "private Compose network adapter missing")
        spec = importlib.util.spec_from_file_location("network_driver", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_compose_preserves_checker_and_uses_environment_references(self):
        driver = self.driver()
        with tempfile.TemporaryDirectory() as d:
            cert = certificate(d)
            for original_env in ({"CHECKER": "keep"}, ["CHECKER=keep"]):
                original = {"services": {"sim": {"image": "prepared-image",
                            "environment": original_env, "command": ["pytest", "private_checker.py"],
                            "build": {"context": ".", "args": ["KEEP=value"]},
                            "volumes": ["./private:/tests:ro"]}}}
                data = copy.deepcopy(original)
                driver.configure_compose(data, {"HTTPS_PROXY": "http://user:secret@proxy", "NO_PROXY": "localhost",
                                                "AGENT_OPT_CA_BUNDLE": str(cert), "MODEL_API_KEY": "never"})
                service = data["services"]["sim"]
                self.assertEqual(service["environment"]["CHECKER"], "keep")
                self.assertIsNone(service["environment"]["HTTPS_PROXY"])
                self.assertIsNone(service["build"]["args"]["https_proxy"])
                self.assertEqual(service["build"]["args"]["KEEP"], "value")
                self.assertEqual(service["command"], original["services"]["sim"]["command"])
                self.assertEqual(service["volumes"][0], "./private:/tests:ro")
                self.assertTrue(all(v["read_only"] for v in service["volumes"][1:]))
                serialized = json.dumps(data)
                self.assertNotIn("secret", serialized)
                self.assertNotIn("MODEL_API_KEY", serialized)

    def test_evaluator_keeps_network_but_filters_model_credentials(self):
        from test_dev_environment import cvdp as evaluator, official_row, prepare
        from agent_optimizer.contracts import Task
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            output = root / "output"
            (output / "rtl").mkdir(parents=True)
            (output / "rtl/dut.sv").write_text("module dut; endmodule")
            task = Task(**prepare.convert([official_row()])[0][0])
            env = {"HTTPS_PROXY": "http://proxy", "NO_PROXY": "local.test", "MODEL_API_KEY": "secret"}
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(evaluator, "run_process", return_value=ExecutionResult("process_error", 1, 0, "", "")) as run, \
                    patch.object(evaluator, "cleanup_network"):
                evaluator.CVDPEvaluator().evaluate(task, output, 5)
            child_env = run.call_args.kwargs["env"]
            self.assertEqual(child_env.get("https_proxy"), "http://proxy")
            self.assertEqual(child_env.get("NO_PROXY"), "local.test")
            self.assertNotIn("MODEL_API_KEY", child_env)
            self.assertEqual(Path(run.call_args.args[0][1]).name, "network_driver.py")

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "Use existing CVDP driver or uv --with PyYAML for YAML integration")
    def test_private_submission_yaml_round_trip_leaves_source_and_checker_intact(self):
        import yaml
        from test_dev_environment import official_row
        driver = self.driver()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "submission.jsonl"
            original = json.dumps(official_row()) + "\n"
            path.write_text(original)
            new = driver.configure_submission(path, {"HTTPS_PROXY": "http://user:secret@proxy", "NO_PROXY": "local.test"})
            self.assertEqual(path.read_text(), original)
            result = json.loads(new.read_text())
            self.assertEqual(result["harness"]["files"]["src/test_runner.py"], "PRIVATE_CHECKER")
            compose = yaml.safe_load(result["harness"]["files"]["docker-compose.yml"])
            self.assertIsNone(compose["services"]["direct"]["environment"]["HTTPS_PROXY"])
            self.assertNotIn("secret", new.read_text())

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "Use existing CVDP driver or uv --with PyYAML for driver integration")
    def test_evaluator_launches_real_wrapper_and_reads_driver_result(self):
        from test_dev_environment import cvdp, official_row, prepare
        from agent_optimizer.contracts import Task
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # A tiny official-driver contract fixture, not a real CVDP evaluation.
            (root / "run_benchmark.py").write_text(
                "import sys,json,yaml\nfrom pathlib import Path\n"
                "a=sys.argv; row=json.loads(Path(a[a.index('-f')+1]).read_text())\n"
                "assert a[a.index('--network-name')+1].startswith('agent-opt-cvdp-')\n"
                "service=yaml.safe_load(row['harness']['files']['docker-compose.yml'])['services']['direct']\n"
                "assert service['environment']['HTTPS_PROXY'] is None\n"
                "assert row['harness']['files']['src/test_runner.py']=='PRIVATE_CHECKER'\n"
                "out=Path(a[a.index('-p')+1]); out.mkdir()\n"
                "(out/'raw_result.json').write_text(json.dumps({row['id']:{'tests':[{'result':0}]}}))\n")
            output = root / "output"
            (output / "rtl").mkdir(parents=True)
            (output / "rtl/dut.sv").write_text("module dut; endmodule")
            evaluator = cvdp.CVDPEvaluator()
            evaluator.repo, evaluator.python = root, Path(sys.executable)
            task = Task(**prepare.convert([official_row()])[0][0])
            with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.invalid"}, clear=True), \
                    patch.object(cvdp, "cleanup_network"):
                result = evaluator.evaluate(task, output, 10)
            self.assertEqual(result.status, "passed", (root / "cvdp_evaluation/logs/stderr.log").read_text())
            original = json.loads((root / "cvdp_evaluation/submission.jsonl").read_text())
            self.assertNotIn("HTTPS_PROXY", original["harness"]["files"]["docker-compose.yml"])


@unittest.skipUnless(os.environ.get("AGENT_OPT_NETWORK_DOCKER") == "1", "Set AGENT_OPT_NETWORK_DOCKER=1 for BuildKit integration")
class DockerNetworkIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("yaml"), "Compose integration needs the existing driver PyYAML")
    def test_actual_compose_receives_proxy_and_readonly_ca(self):
        import yaml
        from agent_optimizer.network import host_environment
        driver = EvaluatorNetworkTests().driver()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            root = Path(d)
            root.chmod(0o755)
            cert = certificate(d)
            cert.chmod(0o644)
            env = host_environment({**os.environ, "https_proxy": "http://user:secret@proxy.invalid:3128",
                                    "no_proxy": "localhost", "AGENT_OPT_CA_BUNDLE": str(cert)})
            code = ("import os,ssl; assert ssl.create_default_context().get_ca_certs(); "
                    "assert os.environ['HTTPS_PROXY'].endswith('proxy.invalid:3128'); "
                    "assert os.environ['NO_PROXY'] == 'localhost'; print('compose passed')")
            data = {"services": {"probe": {"image": "python:3.12-slim-bookworm",
                    "network_mode": "none", "command": ["python", "-c", code]}}}
            driver.configure_compose(data, env)
            file = root / "compose.yml"
            file.write_text(yaml.safe_dump(data))
            self.assertNotIn("secret", file.read_text())
            command = ["docker", "compose", "-f", str(file), "-p", "network-" + uuid.uuid4().hex[:12]]
            try:
                result = subprocess.run([*command, "run", "--rm", "probe"], env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("compose passed", result.stdout)
            finally:
                subprocess.run([*command, "down"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_actual_build_trust_proxy_history_and_runtime_readonly_ca(self):
        from agent_optimizer.network import configured_build, host_environment
        # Colima shares the workspace, not macOS /private/var temporary directories.
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            root = Path(d)
            root.chmod(0o755)
            cert = certificate(d)
            cert.chmod(0o644)
            marker = "http://user:network-test-secret@proxy.invalid:3128"
            # Pull using the real host environment, then use a local-only tag:
            # Buildx's registry auth client also honors the test proxy environment.
            subprocess.run(["docker", "pull", "python:3.12-slim-bookworm"], check=True, timeout=180)
            base = "agent-opt-network-base:" + uuid.uuid4().hex[:12]
            subprocess.run(["docker", "tag", "python:3.12-slim-bookworm", base], check=True)
            self.addCleanup(subprocess.run, ["docker", "image", "rm", base],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            recipe = (f"FROM {base}\n"
                      "RUN python -c \"import ssl,os; assert ssl.create_default_context().get_ca_certs(); "
                      "assert os.environ['https_proxy'].startswith('http://user:')\"\n")
            (root / "Dockerfile").write_text(recipe)
            image = "agent-opt-network-test:" + uuid.uuid4().hex[:12]
            self.addCleanup(subprocess.run, ["docker", "image", "rm", "-f", image],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            env = host_environment({**os.environ, "AGENT_OPT_CA_BUNDLE": str(cert),
                                    "https_proxy": marker, "HTTPS_PROXY": marker,
                                    "NO_PROXY": "localhost", "no_proxy": "localhost"})
            with configured_build(["docker", "build", "-f", "Dockerfile", "-t", image, "."], root, env) as argv:
                subprocess.run(argv, cwd=root, env=env, check=True, timeout=180)
            history = subprocess.check_output(["docker", "history", "--no-trunc", image], text=True)
            info = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]
            self.assertNotIn("network-test-secret", history)
            self.assertFalse(any("proxy=" in entry.lower() for entry in info["Config"]["Env"]))
            code = ("import os,ssl; assert ssl.create_default_context().get_ca_certs(); "
                    "assert os.environ['HTTPS_PROXY'] == os.environ['https_proxy']; "
                    "assert os.environ['NO_PROXY'] == 'localhost'; "
                    "print('trust and proxy passed'); "
                    "p=os.environ['SSL_CERT_FILE']; "
                    "exec('try:\\n open(p, \"a\")\\nexcept OSError:\\n print(\"readonly passed\")\\nelse:\\n raise AssertionError(\"writable CA\")')")
            with patch.dict(os.environ, env, clear=True):
                result = execute(["python", "-c", code], root, root / "logs", 30,
                                 {"kind": "docker", "image": image, "network": "none"})
            self.assertEqual(result.status, "completed", Path(result.stderr_path).read_text())
            self.assertIn("readonly passed", Path(result.stdout_path).read_text())


if __name__ == "__main__":
    unittest.main()
