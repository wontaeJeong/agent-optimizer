"""실제 로컬 HTTP 경계에서 SDK fixture의 표준 endpoint를 검사한다."""
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from opencode_endpoint_fixture import Handler, requests


class EndpointFixtureTests(unittest.TestCase):
    def test_standard_completions_route_accepts_streamed_tool_round_trip(self):
        requests.clear()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
            body = {"model": "fixture-model", "stream": True, "messages": [],
                    "tools": [{"type": "function", "function": {"name": "bash"}}]}
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for tool_result in (False, True):
                body["messages"] = [{"role": "tool", "content": "ok"}] if tool_result else []
                request = urllib.request.Request(url, json.dumps(body).encode(), headers={
                    "Authorization": "Bearer fixture-key", "Content-Type": "application/json"})
                with opener.open(request, timeout=5) as response:
                    chunks = [json.loads(line.removeprefix("data: ")) for line in
                              response.read().decode().splitlines()
                              if line.startswith("data: ") and line != "data: [DONE]"]
                if not tool_result:
                    self.assertEqual(chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"], "bash")
                self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "stop" if tool_result else "tool_calls")
            self.assertEqual(len(requests), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
