import json
import os
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from agent_optimizer.contracts import ConfigurationError, UnavailableError
from agent_optimizer.models import ModelSettings, complete, probe_model


@contextmanager
def model_server(responses, *, trickle=False, require_auto_tools=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append({"path": self.path, "authorization": self.headers.get("Authorization"),
                             "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            status, payload = responses[min(len(requests) - 1, len(responses) - 1)]
            if require_auto_tools and (requests[-1]["body"].get("tool_choice") not in (None, "auto")
                                       or not requests[-1]["body"].get("tools")):
                status, payload = 400, {"error": {"message": "Thinking mode does not support this tool_choice"}}
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            if status == 307:
                self.send_header("Location", "/stolen")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                if trickle:
                    for byte in body:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.02)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def completion(content="hello", usage=None):
    value = {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
    if usage is not None:
        value["usage"] = usage
    return value


class ModelTests(unittest.TestCase):
    def test_trickling_response_cannot_extend_total_request_deadline(self):
        with model_server([(200, completion())], trickle=True) as (url, _requests):
            settings = ModelSettings.from_env({"AGENT_OPT_MODEL_ENDPOINT": url + "/chat/completion", "AGENT_OPT_MODEL_API_KEY": "key"})
            started = time.monotonic()
            with self.assertRaises(UnavailableError):
                complete([], settings=settings, timeout=0.5)
            self.assertLess(time.monotonic() - started, 1.5)

    def test_exact_endpoint_and_default_model_reach_server_with_bearer(self):
        with model_server([(200, completion())]) as (url, requests), patch.dict(os.environ, {
            "AGENT_OPT_MODEL_ENDPOINT": url + "/v1/chat/completion", "AGENT_OPT_MODEL_API_KEY": "fixture-secret",
        }, clear=True):
            self.assertEqual(complete([{"role": "user", "content": "hi"}])["choices"][0]["message"]["content"], "hello")
            self.assertEqual(requests[0]["path"], "/v1/chat/completion")
            self.assertEqual(requests[0]["authorization"], "Bearer fixture-secret")
            self.assertEqual(requests[0]["body"]["model"], "glm5.3-flash")
            self.assertFalse(requests[0]["body"]["stream"])
            self.assertNotIn("fixture-secret", repr(ModelSettings.from_env()))

    def test_base_url_and_model_override(self):
        with model_server([(200, completion())]) as (url, requests):
            settings = ModelSettings.from_env({"AGENT_OPT_MODEL_BASE_URL": url + "/v1/", "AGENT_OPT_MODEL_API_KEY": "key", "AGENT_OPT_MODEL_ID": "another/model"})
            complete([], settings=settings)
            self.assertEqual(requests[0]["path"], "/v1/chat/completions")
            self.assertEqual(requests[0]["body"]["model"], "another/model")

    def test_invalid_config_is_rejected_before_network(self):
        good = {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1/chat/completion", "AGENT_OPT_MODEL_API_KEY": "key"}
        for update in [{"AGENT_OPT_MODEL_API_KEY": ""}, {"AGENT_OPT_MODEL_ID": ""}, {"AGENT_OPT_MODEL_BASE_URL": "https://example.invalid/v1"},
                       {"AGENT_OPT_MODEL_ENDPOINT": "http://example.invalid/v1"}, {"AGENT_OPT_MODEL_ENDPOINT": "https://key@example.invalid/v1"},
                       {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1?token=secret"}, {"AGENT_OPT_MODEL_API_KEY": "key\nheader"}]:
            with self.subTest(update=update), self.assertRaises((ConfigurationError, UnavailableError)):
                ModelSettings.from_env({**good, **update})

    def test_failures_do_not_echo_credentials_or_remote_body(self):
        for status, body in [(401, b"fixture-secret"), (500, b"fixture-secret"), (307, b"redirect"),
                             (200, b"not-json fixture-secret"), (200, {}), (200, {"choices": []})]:
            with self.subTest(status=status, body=body), model_server([(status, body)]) as (url, requests):
                settings = ModelSettings.from_env({"AGENT_OPT_MODEL_ENDPOINT": url + "/chat/completion", "AGENT_OPT_MODEL_API_KEY": "fixture-secret"})
                with self.assertRaises(UnavailableError) as error:
                    complete([], settings=settings)
                self.assertNotIn("fixture-secret", str(error.exception))
                self.assertEqual(len(requests), 1)

    def test_probe_accepts_default_thinking_mode_and_requires_real_tool_call(self):
        reply = completion(None)
        reply["choices"][0]["message"]["tool_calls"] = [{"id": "call_1", "type": "function", "function": {
            "name": "connectivity_check", "arguments": '{"ok":true}'}}]
        with model_server([(200, reply)], require_auto_tools=True) as (url, requests):
            settings = ModelSettings.from_env({"AGENT_OPT_MODEL_ENDPOINT": url + "/chat/completion", "AGENT_OPT_MODEL_API_KEY": "key"})
            self.assertEqual(probe_model(settings=settings)["status"], "passed")
            self.assertEqual(requests[0]["body"]["tools"][0]["function"]["name"], "connectivity_check")
            self.assertIn(requests[0]["body"].get("tool_choice"), (None, "auto"))
        with model_server([(200, completion())]) as (url, _requests):
            settings = ModelSettings.from_env({"AGENT_OPT_MODEL_ENDPOINT": url + "/chat/completion", "AGENT_OPT_MODEL_API_KEY": "key"})
            with self.assertRaises(UnavailableError):
                probe_model(settings=settings)

    def test_prefixed_only_and_explicit_mapping_isolation(self):
        new = {"AGENT_OPT_MODEL_ENDPOINT": "https://example.invalid/v1/chat/completions",
               "AGENT_OPT_MODEL_API_KEY": "fixture-secret"}
        with patch.dict(os.environ, {"MODEL_ENDPOINT": new["AGENT_OPT_MODEL_ENDPOINT"],
                                     "MODEL_API_KEY": "old-secret"}, clear=True):
            with self.assertRaises((ConfigurationError, UnavailableError)):
                ModelSettings.from_env()
            settings = ModelSettings.from_env(new)
            self.assertEqual(settings.model, "glm5.3-flash")
            self.assertNotIn("fixture-secret", repr(settings))
            with self.assertRaises((ConfigurationError, UnavailableError)):
                ModelSettings.from_env({"MODEL_ENDPOINT": new["AGENT_OPT_MODEL_ENDPOINT"],
                                        "MODEL_API_KEY": "old-secret"})
