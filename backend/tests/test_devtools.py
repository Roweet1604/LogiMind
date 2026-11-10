"""start-dev.bat helpers (backend/scripts/devtools.py): .env set-up never overwrites a value, busy ports are named
and nothing is stopped, and waiting for a server works."""
import importlib.util
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "devtools.py"
SPEC = importlib.util.spec_from_file_location("devtools", SCRIPT)
devtools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(devtools)

EXAMPLE = "# comment\r\nLOGIMIND_DRIVER_LINK_SECRET=\r\nLOGIMIND_WORKER=inline\r\n"


def _secret(text):
    return next(line.split("=", 1)[1] for line in text.splitlines() if line.startswith("LOGIMIND_DRIVER_LINK_SECRET="))


def test_env_is_created_with_a_generated_secret_and_kept_on_the_next_run(tmp_path):
    (tmp_path / ".env.example").write_bytes(EXAMPLE.encode())
    done = devtools.ensure_env(tmp_path)
    assert len(done) == 2
    text = (tmp_path / ".env").read_bytes().decode()
    secret = _secret(text)
    assert len(secret) >= 32 and "\r\n" in text and "LOGIMIND_WORKER=inline" in text
    assert devtools.ensure_env(tmp_path) == []                       # second start: nothing changes
    assert _secret((tmp_path / ".env").read_bytes().decode()) == secret
    assert "LOGIMIND_DRIVER_LINK_SECRET=\r\n" in (tmp_path / ".env.example").read_bytes().decode()  # template untouched


def test_an_existing_secret_is_never_replaced_and_a_missing_line_is_added(tmp_path):
    (tmp_path / ".env.example").write_bytes(EXAMPLE.encode())
    (tmp_path / ".env").write_text("LOGIMIND_DRIVER_LINK_SECRET=" + "k" * 40 + "\n")
    assert devtools.ensure_env(tmp_path) == []
    assert _secret((tmp_path / ".env").read_text()) == "k" * 40
    (tmp_path / ".env").write_text("LOGIMIND_WORKER=inline\n")
    assert len(devtools.ensure_env(tmp_path)) == 1
    assert len(_secret((tmp_path / ".env").read_text())) >= 32


def test_a_busy_port_is_reported_and_left_running(capsys):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]
    try:
        assert devtools.check_ports([port]) == 1
        out = capsys.readouterr().out
        assert f"Port {port} is already in use" in out and "Nothing was stopped" in out
        assert devtools.port_in_use(port)                             # still listening: nothing was killed
    finally:
        srv.close()
    assert devtools.check_ports([port]) == 0


def test_wait_returns_when_the_server_answers_and_fails_when_it_does_not():
    class Ok(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Ok)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        assert devtools.wait_for(f"http://127.0.0.1:{httpd.server_port}/api/health", 10) == 0
    finally:
        httpd.shutdown()
        httpd.server_close()
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    assert devtools.wait_for(f"http://127.0.0.1:{port}/", 1.5) == 1
