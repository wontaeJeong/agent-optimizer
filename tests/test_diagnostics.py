import importlib
import tempfile
import unittest
from pathlib import Path


class DiagnosticSummaryTests(unittest.TestCase):
    def diagnostics(self):
        try:
            return importlib.import_module("agent_optimizer.diagnostics")
        except ModuleNotFoundError as exc:
            self.fail(f"safe subprocess diagnostics are not implemented: {exc}")

    def test_sanitize_removes_secret_values_proxy_userinfo_and_ca_path(self):
        diagnostics = self.diagnostics()
        environment = {
            "OPENROUTER_API_KEY": "SECRET_API_123",
            "CUSTOM_TOKEN": "TOKEN_VALUE_456",
            "HTTPS_PROXY": "http://proxy-user:proxy-pass@proxy.example",
            "AGENT_OPT_CA_BUNDLE": "/private/certs/SECRET-ca.pem",
        }

        text = diagnostics.sanitize_text(
            "key=SECRET_API_123 token=TOKEN_VALUE_456 "
            "proxy=http://proxy-user:proxy-pass@proxy.example "
            "ca=/private/certs/SECRET-ca.pem",
            environment,
        )

        for secret in ("SECRET_API_123", "TOKEN_VALUE_456", "proxy-user", "proxy-pass",
                       "/private/certs/SECRET-ca.pem"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)

    def test_sanitize_redacts_bearer_credentials_and_api_key_is_values(self):
        diagnostics = self.diagnostics()
        cases = (
            ("Authorization: Bearer arbitrary-sensitive-value-123", "arbitrary-sensitive-value-123"),
            ("Authorization: Basic arbitrary-sensitive-value-basic", "arbitrary-sensitive-value-basic"),
            ("Bearer arbitrary-sensitive-value-456", "arbitrary-sensitive-value-456"),
            ("api_key is arbitrary-sensitive-value-789", "arbitrary-sensitive-value-789"),
            ("client_secret=arbitrary-client-value-123", "arbitrary-client-value-123"),
            ("AWS_SECRET_ACCESS_KEY=arbitrary-aws-value-456", "arbitrary-aws-value-456"),
            ("proxy_pass=arbitrary-proxy-value-789", "arbitrary-proxy-value-789"),
        )

        for text, secret in cases:
            with self.subTest(text=text):
                self.assertNotIn(secret, diagnostics.sanitize_text(text))

        outcome = diagnostics.CommandOutcome(
            "docker build", 1,
            stderr="ERROR Authorization: Bearer arbitrary-sensitive-value-123",
        )
        self.assertNotIn(
            "arbitrary-sensitive-value-123", diagnostics.summarize_failure(outcome))

    def test_sanitize_redacts_quoted_json_credential_keys_in_failure_summaries(self):
        diagnostics = self.diagnostics()
        message = ('ERROR {"authorization":"Basic arbitrary-sensitive-basic-123",'
                   '"password":"arbitrary-sensitive-password-456",'
                   '"api_key":"arbitrary-sensitive-key-789",'
                   '"client_secret":"arbitrary-client-value-123",'
                   '"AWS_SECRET_ACCESS_KEY":"arbitrary-aws-value-456",'
                   '"proxy_pass":"arbitrary-proxy-value-789"}')
        outcome = diagnostics.CommandOutcome("git clone", 128, stderr=message)

        summary = diagnostics.summarize_failure(outcome)

        secrets = ("arbitrary-sensitive-basic-123", "arbitrary-sensitive-password-456",
                   "arbitrary-sensitive-key-789", "arbitrary-client-value-123",
                   "arbitrary-aws-value-456", "arbitrary-proxy-value-789")
        for secret in secrets:
            with self.subTest(secret=secret):
                self.assertNotIn(secret, summary)
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "failure.log"
            log.write_text(message)
            summarized_log = "\n".join(diagnostics.summarize_log(log))
        for secret in secrets:
            with self.subTest(log_secret=secret):
                self.assertNotIn(secret, summarized_log)

    def test_failure_classifier_distinguishes_missing_timeout_permission_docker_tls_dns_and_cache(self):
        diagnostics = self.diagnostics()
        cases = [
            (diagnostics.CommandOutcome("uv", None, error_kind="missing"), "not found"),
            (diagnostics.CommandOutcome("uv sync", None, timed_out=True, error_kind="timeout"),
             "timed out"),
            (diagnostics.CommandOutcome("docker info", 1, stderr="permission denied"), "permission"),
            (diagnostics.CommandOutcome("docker info", 1, stderr="cannot connect to docker socket"),
             "daemon"),
            (diagnostics.CommandOutcome("docker build", 1,
                                        stderr="x509 certificate signed by unknown authority"), "TLS"),
            (diagnostics.CommandOutcome("git clone", 1,
                                        stderr="temporary failure in name resolution"), "DNS"),
            (diagnostics.CommandOutcome("uv sync", 1, stderr="package not found in cache"), "cache"),
        ]

        for outcome, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected.lower(), diagnostics.summarize_failure(outcome).lower())

    def test_log_summary_is_bounded_and_redacts_timeout_and_proxy_secrets(self):
        diagnostics = self.diagnostics()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "evaluation-build.log"
            log.write_text(
                "download started\n" * 50
                + "ERROR x509 certificate signed by unknown authority\n"
                + "proxy=http://proxy-user:SECRET_PROXY@proxy.example\n"
            )

            rows = diagnostics.summarize_log(
                log,
                environment={"TOKEN": "SECRET_TOKEN", "HTTPS_PROXY": "http://proxy-user:SECRET_PROXY@proxy.example"},
                limit=3,
            )

        self.assertLessEqual(len(rows), 3)
        self.assertTrue(any("x509" in row.lower() for row in rows))
        output = "\n".join(rows)
        self.assertNotIn("SECRET_PROXY", output)
        self.assertNotIn("SECRET_TOKEN", output)
        self.assertNotIn("proxy-user", output)

    def test_sanitize_redacts_model_values_and_timeout_text_without_echoing_raw_output(self):
        diagnostics = self.diagnostics()
        environment = {
            "AGENT_OPT_MODEL_API_KEY": "SECRET_MODEL_KEY",
            "AGENT_OPT_MODEL_ID": "SECRET_MODEL_ID",
            "CUSTOM_PASSWORD": "SECRET_PASSWORD",
        }
        outcome = diagnostics.CommandOutcome(
            "python",
            None,
            stdout="SECRET_MODEL_ID SECRET_MODEL_KEY",
            stderr="SECRET_PASSWORD request timed out",
            timed_out=True,
            error_kind="timeout",
        )

        summary = diagnostics.summarize_failure(outcome, environment=environment)

        self.assertIn("timed out", summary.lower())
        for secret in environment.values():
            self.assertNotIn(secret, summary)
        self.assertNotIn("SECRET_MODEL_ID", summary)

    def test_exception_summary_keeps_permission_cause_and_redacts_environment_values(self):
        diagnostics = self.diagnostics()
        summarize = getattr(diagnostics, "summarize_exception", None)
        self.assertIsNotNone(summarize, "broad doctor catches need a safe exception summary")
        environment = {
            "AGENT_OPT_CA_BUNDLE": "/private/certs/SECRET_CA.pem",
            "AGENT_OPT_MODEL_API_KEY": "SECRET_API_VALUE",
        }

        summary = summarize(
            PermissionError("permission denied reading /private/certs/SECRET_CA.pem SECRET_API_VALUE"),
            environment=environment,
        )

        self.assertIn("permission denied", summary.lower())
        self.assertNotIn("SECRET_CA.pem", summary)
        self.assertNotIn("SECRET_API_VALUE", summary)

    def test_sanitize_redacts_secret_markers_in_timeout_output_without_environment_values(self):
        diagnostics = self.diagnostics()
        text = diagnostics.sanitize_text("docker run timed out: SECRET_TIMEOUT TOKEN_FIXTURE API_KEY_VALUE")
        for marker in ("SECRET_TIMEOUT", "TOKEN_FIXTURE", "API_KEY_VALUE"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
