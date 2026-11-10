"""Helpers for start-dev.bat (decision 0030). Standard library only, so it runs right after the venv is created.

  python scripts/devtools.py env              create backend/.env from .env.example if missing, and fill an empty
                                              LOGIMIND_DRIVER_LINK_SECRET with a new random value (never printed)
  python scripts/devtools.py ports 8000 5173  exit 1 and say which port is busy (and by which program) if any is
  python scripts/devtools.py wait URL [S]     wait up to S seconds (default 120) until URL answers with HTTP < 500
"""
from __future__ import annotations

import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SECRET_VAR = "LOGIMIND_DRIVER_LINK_SECRET"


def ensure_env(backend: Path = BACKEND) -> list[str]:
    """Returns what was done, in plain words. Existing values are never changed."""
    env, example = backend / ".env", backend / ".env.example"
    done = []
    if not env.exists():
        env.write_bytes(example.read_bytes())
        done.append("created backend\\.env from backend\\.env.example")
    raw = env.read_bytes().decode("utf-8")
    pattern = re.compile(rf"^{SECRET_VAR}=[ \t]*(\r?)$", re.MULTILINE)
    if pattern.search(raw):
        raw = pattern.sub(lambda m: f"{SECRET_VAR}={secrets.token_urlsafe(48)}{m.group(1)}", raw, count=1)
        env.write_bytes(raw.encode("utf-8"))
        done.append(f"generated {SECRET_VAR} in backend\\.env (driver links now survive restarts)")
    elif not re.search(rf"^{SECRET_VAR}=\S", raw, re.MULTILINE):
        nl = "\r\n" if "\r\n" in raw else "\n"
        sep = "" if raw.endswith("\n") or not raw else nl
        raw = f"{raw}{sep}{SECRET_VAR}={secrets.token_urlsafe(48)}{nl}"
        env.write_bytes(raw.encode("utf-8"))
        done.append(f"added {SECRET_VAR} to backend\\.env")
    return done


def port_in_use(port: int) -> bool:
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def who_listens(port: int) -> str:
    """'python.exe (process 1234)' from netstat + tasklist on Windows; '' if it cannot be found."""
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
        out += subprocess.run(["netstat", "-ano", "-p", "TCPv6"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    rows = [p for p in (line.split() for line in out.splitlines())
            if len(p) >= 5 and p[1].endswith(f":{port}") and p[4] != "0"]
    # Seen on this laptop: a Vite server answering on [::1] had no LISTENING row, only its open connections.
    rows.sort(key=lambda p: p[3] != "LISTENING")
    for parts in rows[:1]:
        if parts[3] in ("LISTENING", "ESTABLISHED", "FIN_WAIT_2", "CLOSE_WAIT"):
            pid = parts[4]
            try:
                row = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                     capture_output=True, text=True, timeout=10).stdout.strip()
                name = row.split('","')[0].strip('"') if row.startswith('"') else "a program"
            except (OSError, subprocess.SubprocessError):
                name = "a program"
            return f"{name} (process {pid})"
    return ""


def check_ports(ports: list[int]) -> int:
    busy = [p for p in ports if port_in_use(p)]
    for p in busy:
        owner = who_listens(p)
        print(f"[busy] Port {p} is already in use{' by ' + owner if owner else ''}.")
    if busy:
        print("       Nothing was stopped. Close that program (or the old LogiMind windows)")
        print("       and run start-dev.bat again,")
        print("       or choose other ports, e.g.  set CONSOLE_PORT=5183  before start-dev.bat.")
        return 1
    return 0


def wait_for(url: str, timeout_s: float = 120.0) -> int:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return 0
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return 0
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    print(f"[error] {url} did not answer within {timeout_s:.0f} s. Look at the LogiMind windows for the error.")
    return 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["env"]:
        for line in ensure_env():
            print(f"[setup] {line}")
        return 0
    if argv[:1] == ["ports"] and len(argv) > 1:
        return check_ports([int(p) for p in argv[1:]])
    if argv[:1] == ["wait"] and len(argv) in (2, 3):
        return wait_for(argv[1], float(argv[2]) if len(argv) == 3 else 120.0)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
