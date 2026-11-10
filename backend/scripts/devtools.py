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


# ---- ports (decision 0034) ----------------------------------------------------------------------------------
# A port counts as busy ONLY if the operating system lists a LISTENING socket on it. On Windows that list is read
# directly with GetExtendedTcpTable(TCP_TABLE_OWNER_PID_LISTENER), the table netstat itself uses. Measured on this
# laptop (Windows 10.0.26300): listener rows there carry invalid state values (1, 0 or 6 instead of 2 = LISTEN), so
# netstat printed them as CLOSED or not at all while the ports were really in use. The listener table class returns
# only listeners, so the state field is ignored. TIME_WAIT and other connections never count; nothing is bound or
# connected to decide.
TCP_TABLE_OWNER_PID_LISTENER = 3


def _win_listeners(family: int) -> list[tuple[str, int, int]]:
    import ctypes
    import struct
    from ctypes import wintypes

    iphlpapi = ctypes.WinDLL("iphlpapi")
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_LISTENER, 0)
    for _ in range(3):  # the table can grow between the two calls
        buf = ctypes.create_string_buffer(size.value + 4096)
        size = wintypes.DWORD(len(buf))
        rc = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_LISTENER, 0)
        if rc == 0:
            break
    else:
        raise OSError(f"GetExtendedTcpTable failed ({rc})")
    n = struct.unpack_from("I", buf, 0)[0]
    out = []
    for i in range(n):
        if family == socket.AF_INET:  # MIB_TCPROW_OWNER_PID: state, laddr, lport, raddr, rport, pid
            _state, laddr, lport, _ra, _rp, pid = struct.unpack_from("IIIIII", buf, 4 + i * 24)
            addr = socket.inet_ntoa(struct.pack("I", laddr))
        else:  # MIB_TCP6ROW_OWNER_PID: laddr[16], scope, lport, raddr[16], scope, rport, state, pid (56 bytes)
            base = 4 + i * 56
            addr = socket.inet_ntop(socket.AF_INET6, buf.raw[base:base + 16])
            lport, = struct.unpack_from("I", buf, base + 20)
            pid, = struct.unpack_from("I", buf, base + 52)
        out.append((addr, socket.ntohs(lport & 0xFFFF), pid))
    return out


def listeners() -> list[tuple[str, int, int]]:
    """(local address, port, pid) of every LISTENING TCP socket (IPv4 and IPv6)."""
    if sys.platform == "win32":
        return _win_listeners(socket.AF_INET) + _win_listeners(socket.AF_INET6)
    return _proc_listeners()


def _proc_listeners() -> list[tuple[str, int, int]]:
    """Linux: /proc/net/tcp{,6} rows in state 0A (LISTEN); the pid is not resolved (0)."""
    out = []
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(name).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) > 3 and parts[3] == "0A":
                addr, port = parts[1].rsplit(":", 1)
                out.append((addr, int(port, 16), 0))
    return out


def process_name(pid: int) -> str:
    """Executable name of a process ('' if it cannot be read, e.g. a protected system process)."""
    if sys.platform != "win32" or pid <= 0:
        return ""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return Path(buf.value).name
        finally:
            kernel32.CloseHandle(handle)
    try:  # fallback, e.g. for processes of another user
        row = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return row.split('","')[0].strip('"') if row.startswith('"') else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def excluded_ranges(text: str | None = None) -> list[tuple[int, int]]:
    """Windows' reserved TCP port ranges (netsh ... show excludedportrange): no program can listen there."""
    if text is None:
        if sys.platform != "win32":
            return []
        text = ""
        for ver in ("ipv4", "ipv6"):
            try:
                text += subprocess.run(["netsh", "interface", ver, "show", "excludedportrange", "protocol=tcp"],
                                       capture_output=True, text=True, timeout=10).stdout
            except (OSError, subprocess.SubprocessError):
                pass
    return [(int(a), int(b)) for a, b in re.findall(r"^\s*(\d+)\s+(\d+)", text, re.MULTILINE)]


def port_report(ports: list[int], rows: list[tuple[str, int, int]] | None = None,
                reserved: list[tuple[int, int]] | None = None) -> list[str]:
    """One plain line per port that cannot be used: who LISTENS on it (pid and name), or that Windows reserves it."""
    rows = listeners() if rows is None else rows
    reserved = excluded_ranges() if reserved is None else reserved
    lines = []
    for port in ports:
        holders = sorted({(pid, addr) for addr, p, pid in rows if p == port})
        if holders:
            who = "; ".join(f"{process_name(pid) or 'unknown program'} (PID {pid}) on {addr}" for pid, addr in holders)
            lines.append(f"[busy] Port {port} is in use: something is LISTENING on it: {who}.")
        elif any(a <= port <= b for a, b in reserved):
            lines.append(f"[reserved] Port {port} is reserved by Windows (excluded port range); no program can "
                         "listen on it. Choose another port.")
    return lines


def check_ports(ports: list[int]) -> int:
    try:
        lines = port_report(ports)
    except OSError as exc:
        print(f"[note] Could not read the list of listening ports ({exc}); the ports were not checked.")
        return 0
    for line in lines:
        print(line)
    if lines:
        print("       Nothing was stopped. Close that program (or the old LogiMind windows) and run start-dev.bat")
        print("       again, or choose other ports (e.g.  set CONSOLE_PORT=5183), or skip this check with")
        print("       start-dev.bat --force-ports  (the servers then fail by themselves if a port is really taken).")
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
