"""Run inside the pinned Agent image; no external network/model is used."""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

requests = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append((self.path, self.headers.get("Authorization"), data))
        assert self.path == "/v1/chat/completion", self.path
        assert self.headers.get("Authorization") == "Bearer fixture-key"
        assert data["model"] == "fixture-model"
        tools = [tool["function"]["name"] for tool in data.get("tools", [])]
        already_called = any(message.get("role") == "tool" for message in data["messages"])
        if "bash" in tools and not already_called:
            delta = {"role": "assistant", "content": None, "tool_calls": [{"index": 0, "id": "fixture_call",
                     "type": "function", "function": {"name": "bash", "arguments": json.dumps({
                         "command": "printf fixture-tool-ok > probe.txt", "description": "Write fixture proof"})}}]}
            reason = "tool_calls"
        else:
            delta = {"role": "assistant", "content": "Fixture complete."}
            reason = "stop"
        chunks = [{"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture-model",
                   "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                  {"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture-model",
                   "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}]
        if data.get("stream"):
            body = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
            kind = "text/event-stream"
        else:
            body = json.dumps({"id": "fixture", "object": "chat.completion", "created": 1, "model": "fixture-model",
                               "choices": [{"index": 0, "message": delta, "finish_reason": reason}]}).encode()
            kind = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    env = {**os.environ, "AGENT_OPT_MODEL_ENDPOINT": f"http://127.0.0.1:{server.server_port}/v1/chat/completion",
           "AGENT_OPT_MODEL_API_KEY": "fixture-key", "AGENT_OPT_MODEL_ID": "fixture-model",
           "OPENCODE_CONFIG": "/opt/agent-optimizer/compatible.json", "OPENCODE_DISABLE_MODELS_FETCH": "true"}
    env.pop("AGENT_OPT_MODEL_BASE_URL", None)
    result = subprocess.run(["opencode", "run", "--format", "json", "--model", "compatible/fixture-model",
                             "Use bash to write fixture-tool-ok into probe.txt, then stop."],
                            env=env, capture_output=True, text=True, timeout=100)
    Path("stdout.log").write_text(result.stdout)
    Path("stderr.log").write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert not any(event.get("type") == "error" for event in events), result.stdout
    assert Path("probe.txt").read_text() == "fixture-tool-ok", result.stdout
    assert len(requests) >= 2 and any(r[2].get("stream") for r in requests)
    assert any(any(m.get("role") == "tool" for m in r[2]["messages"]) for r in requests)
    print(json.dumps({"status": "passed", "requests": len(requests), "streaming": True, "tool_execution": True}))
finally:
    server.shutdown()
    server.server_close()
    thread.join()
