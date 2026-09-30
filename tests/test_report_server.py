from __future__ import annotations

import contextlib
import http.client
import importlib
import io
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit


class ReportServerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("agent_optimizer.report_server"),
                             "보고서 서버 backend가 구현되어야 합니다")
        self.module = importlib.import_module("agent_optimizer.report_server")
        self.temp = tempfile.TemporaryDirectory(prefix="report-server-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.report = self.run / "report.html"
        self.html = "<!doctype html><html><body>보고서</body></html>".encode()
        self.report.write_bytes(self.html)

    def start(self, **kwargs):
        handle = self.module.start_report_server(self.report, **kwargs)
        self.addCleanup(handle.close)
        return handle

    def request(self, handle, path="/report.html", method="GET", headers=None):
        url = urlsplit(handle.url)
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=3)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_import_has_no_bind_or_browser_side_effects(self):
        with patch("socket.socket.bind", side_effect=AssertionError("bind")), patch(
            "webbrowser.open", side_effect=AssertionError("browser")
        ):
            importlib.reload(self.module)

    def test_actual_url_get_head_root_and_headers(self):
        handle = self.start()
        self.assertEqual(urlsplit(handle.url).hostname, "127.0.0.1")
        self.assertGreater(urlsplit(handle.url).port, 0)
        self.assertEqual(urlsplit(handle.url).path, "/report.html")
        for path in ("/", "/report.html"):
            status, headers, body = self.request(handle, path)
            self.assertEqual((status, body), (200, self.html))
            self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.assertEqual(headers["Content-Length"], str(len(self.html)))
        status, headers, body = self.request(handle, method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["Content-Length"], str(len(self.html)))

    def test_unapproved_files_and_host_are_not_exposed_or_logged(self):
        for name in (".env", "report.json", "summary.json", "manifest.json", "events.jsonl"):
            (self.run / name).write_text("PRIVATE_SENTINEL")
        for name in ("private", "candidate", "source"):
            (self.run / name).mkdir()
            (self.run / name / "secret.html").write_text("PRIVATE_SENTINEL")
        handle = self.start()
        with contextlib.redirect_stderr(io.StringIO()) as output:
            for path in ("/.env", "/report.json", "/summary.json", "/manifest.json",
                         "/events.jsonl", "/private/", "/candidate/secret.html",
                         "/source/secret.html", "/missing", "/index.html"):
                with self.subTest(path=path):
                    status, _, body = self.request(handle, path)
                    self.assertEqual(status, 404)
                    self.assertNotIn(b"PRIVATE_SENTINEL", body)
                    self.assertNotIn(str(self.root).encode(), body)
            self.assertEqual(self.request(handle, headers={"Host": "evil.example"})[0], 404)
        self.assertEqual(output.getvalue(), "")

    def test_noncanonical_urls_are_rejected(self):
        handle = self.start()
        paths = ("/../report.html", "/%2e%2e/report.html", "/%252e%252e/report.html",
                 "/%2freport.html", "/%252freport.html", "/%5creport.html",
                 "/%255creport.html", "/%72eport.html", "/report.html%00",
                 "/report.html?file=.env", "/report.html?", "/report.html#secret",
                 "/report.html#", "/report.html/", "/./report.html", "//report.html",
                 "/\\report.html", "http://127.0.0.1/report.html", "/%GG")
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.request(handle, path)[0], 404)

    def test_only_get_and_head_are_allowed(self):
        handle = self.start()
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT"):
            with self.subTest(method=method):
                status, headers, _ = self.request(handle, method=method)
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET, HEAD")
        self.assertEqual(self.report.read_bytes(), self.html)

    def test_missing_directory_symlink_special_and_unapproved_input_fail(self):
        missing = self.run / "absent" / "report.html"
        cases = [(missing, "missing_report"), (self.run, "unsafe_report")]
        private = self.root / "private.html"
        private.write_text("PRIVATE_SENTINEL")
        link = self.run / "index.html"
        link.symlink_to(private)
        cases.append((link, "unsafe_report"))
        fifo_dir = self.root / "fifo"
        fifo_dir.mkdir()
        fifo = fifo_dir / "report.html"
        os.mkfifo(fifo)
        cases.append((fifo, "unsafe_report"))
        linked_run = self.root / "linked"
        linked_run.symlink_to(self.run, target_is_directory=True)
        cases.append((linked_run / "report.html", "unsafe_report"))
        nested = self.run / "nested"
        nested.mkdir()
        (nested / "report.html").write_bytes(self.html)
        cases.append((linked_run / "nested" / "report.html", "unsafe_report"))
        other = self.run / ".env.html"
        other.write_text("PRIVATE_SENTINEL")
        cases.append((other, "unsafe_report"))
        cases.append((self.run / ".." / "run" / "report.html", "unsafe_report"))
        for path, code in cases:
            with self.subTest(path=path), self.assertRaises(self.module.ReportServerError) as raised:
                self.module.start_report_server(path)
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn(str(self.root), str(raised.exception))
            self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))
        self.assertFalse(missing.parent.exists())

    def test_file_swap_and_root_swap_cannot_publish_private_data(self):
        handle = self.start()
        private = self.root / "private.html"
        private.write_text("PRIVATE_SENTINEL")
        self.report.unlink()
        self.report.symlink_to(private)
        self.assertEqual(self.request(handle)[0], 404)
        self.report.unlink()
        self.report.write_text("PRIVATE_SENTINEL")
        self.assertEqual(self.request(handle)[0], 404)
        old = self.root / "old"
        self.run.rename(old)
        self.run.mkdir()
        (self.run / "report.html").write_text("PRIVATE_SENTINEL")
        self.assertEqual(self.request(handle)[0], 404)

    def test_symlink_swap_at_actual_open_is_not_followed(self):
        handle = self.start()
        private = self.root / "private.html"
        private.write_text("PRIVATE_SENTINEL")
        original_open = os.open
        swapped = False

        def racing_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "report.html" and not swapped:
                swapped = True
                self.report.unlink()
                self.report.symlink_to(private)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(self.module.os, "open", side_effect=racing_open):
            status, _, body = self.request(handle)
        self.assertTrue(swapped)
        self.assertEqual(status, 404)
        self.assertNotIn(b"PRIVATE_SENTINEL", body)

    def test_in_place_changes_do_not_change_approved_snapshot(self):
        handle = self.start()
        self.report.write_text("PRIVATE_SENTINEL")
        status, _, body = self.request(handle)
        self.assertEqual((status, body), (200, self.html))

    def test_port_validation_and_conflict_have_explicit_diagnostics(self):
        for port in (-1, 65536, True, 1.5, "80", None):
            with self.subTest(port=port), self.assertRaises(self.module.ReportServerError) as raised:
                self.start(port=port)
            self.assertEqual(raised.exception.code, "invalid_port")
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            with self.assertRaises(self.module.ReportServerError) as raised:
                self.start(port=port)
            self.assertEqual(raised.exception.code, "port_in_use")
            self.assertIn(f"127.0.0.1:{port}", str(raised.exception))
            self.assertIsNotNone(raised.exception.errno)

    def test_close_concurrent_idempotent_releases_thread_and_port_and_restarts(self):
        before = set(threading.enumerate())
        handle = self.start()
        port = urlsplit(handle.url).port
        self.assertEqual(self.request(handle)[0], 200)
        self.assertEqual(self.request(handle)[0], 200)
        closing = [threading.Thread(target=handle.close) for _ in range(3)]
        for thread in closing:
            thread.start()
        for thread in closing:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        handle.close()
        self.assertEqual(set(threading.enumerate()), before)
        with socket.socket() as probe:
            probe.settimeout(0.5)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
        restarted = self.start(port=port)
        self.assertEqual(urlsplit(restarted.url).port, port)
        self.assertEqual(self.request(restarted)[0], 200)

    def test_close_cleans_up_partial_http_client(self):
        handle = self.start()
        port = urlsplit(handle.url).port
        with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
            client.sendall(b"GET /report.html HTTP/1.1\r\n")
            closer = threading.Thread(target=handle.close)
            closer.start()
            closer.join(3)
            self.assertFalse(closer.is_alive())
        with socket.socket() as probe:
            probe.settimeout(0.5)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)

    def test_close_interrupts_a_client_that_keeps_sending_partial_headers(self):
        handle = self.start()
        port = urlsplit(handle.url).port
        stop = threading.Event()
        sent = threading.Event()
        with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
            client.sendall(b"GET /report.html HTTP/1.1\r\nX-Slow: ")

            def drip():
                while not stop.wait(0.05):
                    try:
                        client.sendall(b"x")
                        sent.set()
                    except OSError:
                        break

            sender = threading.Thread(target=drip)
            sender.start()
            self.assertTrue(sent.wait(1))
            closer = threading.Thread(target=handle.close)
            closer.start()
            try:
                closer.join(1)
                self.assertFalse(closer.is_alive())
            finally:
                stop.set()
                sender.join(1)
                with contextlib.suppress(OSError):
                    client.shutdown(socket.SHUT_RDWR)
                closer.join(3)

    def test_index_is_only_a_single_html_and_does_not_follow_session_links(self):
        index = self.run / "index.html"
        body = b'<html><a href="child/report.html">child</a></html>'
        index.write_bytes(body)
        handle = self.module.start_report_server(index)
        self.addCleanup(handle.close)
        self.assertEqual(urlsplit(handle.url).path, "/index.html")
        self.assertEqual(self.request(handle, "/index.html")[2], body)
        self.assertEqual(self.request(handle, "/")[2], body)
        self.assertEqual(self.request(handle, "/child/report.html")[0], 404)
        self.assertEqual(self.request(handle, "/report.html")[0], 404)

    def test_read_and_bind_errors_map_errno_without_private_messages(self):
        import errno

        with patch.object(self.module.os, "open", side_effect=PermissionError(
            errno.EACCES, "PRIVATE_SENTINEL", str(self.report)
        )):
            with self.assertRaises(self.module.ReportServerError) as raised:
                self.start()
        self.assertEqual((raised.exception.code, raised.exception.errno),
                         ("report_unreadable", errno.EACCES))
        self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))
        self.assertNotIn(str(self.report), str(raised.exception))
        with patch("socket.socket.bind", side_effect=OSError(errno.EACCES, "PRIVATE_SENTINEL")):
            with self.assertRaises(self.module.ReportServerError) as raised:
                self.start()
        self.assertEqual((raised.exception.code, raised.exception.errno),
                         ("bind_failed", errno.EACCES))
        self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))

    def test_special_replacement_and_hardlinks_are_refused(self):
        handle = self.start()
        self.report.unlink()
        os.mkfifo(self.report)
        self.assertEqual(self.request(handle)[0], 404)
        self.report.unlink()
        self.report.mkdir()
        self.assertEqual(self.request(handle)[0], 404)
        self.report.rmdir()
        self.report.write_bytes(self.html)
        os.link(self.report, self.root / "linked.html")
        with self.assertRaises(self.module.ReportServerError) as raised:
            self.start()
        self.assertEqual(raised.exception.code, "unsafe_report")

    def test_thread_start_failure_releases_bound_socket(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with patch("threading.Thread.start", side_effect=RuntimeError("PRIVATE_SENTINEL")):
            with self.assertRaises(self.module.ReportServerError) as raised:
                self.start(port=port)
        self.assertEqual(raised.exception.code, "start_failed")
        self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))
        handle = self.start(port=port)
        self.assertEqual(self.request(handle)[0], 200)


if __name__ == "__main__":
    unittest.main()
