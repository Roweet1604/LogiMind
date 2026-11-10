"""start-dev.bat helpers (backend/scripts/devtools.py): .env set-up never overwrites a value, busy ports are named
and nothing is stopped, and waiting for a server works."""
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
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


WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows listener table")


def _listener(family=socket.AF_INET, host="127.0.0.1"):
    srv = socket.socket(family, socket.SOCK_STREAM)
    srv.bind((host, 0))
    srv.listen()
    return srv, srv.getsockname()[1]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@WINDOWS
def test_a_real_ipv4_listener_is_busy_with_its_pid_and_name_and_left_running(capsys):
    srv, port = _listener()
    try:
        assert devtools.check_ports([port]) == 1
        out = capsys.readouterr().out
        assert f"[busy] Port {port} is in use: something is LISTENING on it" in out
        assert f"(PID {os.getpid()}) on 127.0.0.1" in out and "python" in out.lower()
        assert "Nothing was stopped" in out and "--force-ports" in out
        assert any(p == port for _a, p, _pid in devtools.listeners())  # still listening: nothing was killed
    finally:
        srv.close()
    assert devtools.check_ports([port]) == 0


@WINDOWS
def test_a_real_ipv6_listener_is_busy_too():
    srv, port = _listener(socket.AF_INET6, "::1")
    try:
        lines = devtools.port_report([port], reserved=[])
        assert len(lines) == 1 and f"(PID {os.getpid()}) on ::1" in lines[0]
    finally:
        srv.close()


@WINDOWS
def test_free_ports_are_free_and_time_wait_does_not_count():
    assert devtools.port_report([_free_port(), _free_port()], reserved=[]) == []
    srv, port = _listener()
    cli = socket.create_connection(("127.0.0.1", port))
    conn, _ = srv.accept()
    conn.close()  # the server side closes first: its end of the connection goes to TIME_WAIT on `port`
    srv.close()
    cli.close()
    assert devtools.port_report([port], reserved=[]) == []


@WINDOWS
def test_a_successful_connect_alone_never_makes_a_port_busy(monkeypatch):
    # The old check called a port busy when a TCP connect succeeded. Something that accepts connections without a
    # listening socket of its own (a proxy or filter) made that wrong. Only the listener table decides now.
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, addr: 0)
    monkeypatch.setattr(socket.socket, "connect", lambda self, addr: None)
    assert devtools.port_report([_free_port()], reserved=[]) == []


def test_the_report_names_every_holder_and_reserved_ranges():
    rows = [("0.0.0.0", 8000, 99999901), ("::", 8000, 99999901), ("127.0.0.1", 5173, 99999902)]
    lines = devtools.port_report([8000, 5173, 5174, 50010], rows=rows, reserved=[(50000, 50059)])
    assert lines[0].startswith("[busy] Port 8000") and "unknown program (PID 99999901) on 0.0.0.0" in lines[0]
    assert "(PID 99999901) on ::" in lines[0]
    assert lines[1].startswith("[busy] Port 5173") and "(PID 99999902)" in lines[1]
    assert lines[2].startswith("[reserved] Port 50010") and len(lines) == 3  # 5174 is free


def test_windows_excluded_port_ranges_are_parsed():
    text = ("Protocol tcp Port Exclusion Ranges\n\nStart Port    End Port\n----------    --------\n"
            "     27339       27339\n     50000       50059     *\n\n* - Administered port exclusions.\n")
    assert devtools.excluded_ranges(text) == [(27339, 27339), (50000, 50059)]


@WINDOWS
@pytest.mark.skipif(shutil.which("npm") is None, reason="start-dev.bat checks for npm")
def test_start_dev_bat_reports_the_holder_and_force_ports_skips_the_check():
    srv, busy = _listener()
    env = {**os.environ, "API_PORT": str(busy), "CONSOLE_PORT": str(_free_port()), "DRIVER_PORT": str(_free_port()),
           "LOGIMIND_PYTHON": sys.executable}
    try:
        bat = str(ROOT / "start-dev.bat")
        run = subprocess.run(["cmd", "/c", bat, "--dry-run"], cwd=ROOT, env=env, capture_output=True, text=True,
                             timeout=180)
        assert f"[busy] Port {busy} is in use" in run.stdout and f"(PID {os.getpid()})" in run.stdout, run.stdout
        assert "[dry-run] start" in run.stdout
        forced = subprocess.run(["cmd", "/c", bat, "--force-ports", "--dry-run"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=180)
        assert "[skipped] --force-ports" in forced.stdout and "[busy]" not in forced.stdout, forced.stdout
    finally:
        srv.close()


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
