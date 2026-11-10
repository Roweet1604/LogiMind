# 0034: start-dev.bat's port check reads the system's listener table; `--force-ports`

Date: 10 Nov 2026. Status: accepted (asked for by the team). Changes the port check of decision 0030.

## What was reported
`start-dev.bat` said ports 8000, 5173 and 5174 were busy while `netstat -ano | findstr ":8000 :5173 :5174"` printed
nothing.

## What was found (10 Nov 2026, 21:10, this laptop, Windows 10.0.26300)
- **The ports were really in use** by a LogiMind started with `start-dev.bat` at 20:11: the API answered
  `/api/health` on 127.0.0.1:8000 (demo mode, external worker; python.exe PID 3680), and the console and driver Vite
  servers (node.exe 18272 and 27116, started with `--port 5173 --strictPort` / `--port 5174 --strictPort`) answered
  on [::1]:5173 and [::1]:5174.
- **netstat was the unreliable part.** Read directly with `GetExtendedTcpTable(TCP_TABLE_OWNER_PID_LISTENER)` five
  times in a row, the three listeners were always there with their PIDs, but their state field held invalid values
  (1 = "CLOSED", 0 and 6) instead of 2 (LISTEN). netstat turns those values into "CLOSED" or leaves the row out, and two
  netstat runs seconds apart disagreed (8000 missing in one, 5173 "CLOSED" in the other). So `findstr` could print
  nothing for ports that were in use.
- **The old check was weak anyway:** it called a port busy when a TCP connect to 127.0.0.1 or ::1 succeeded, so a
  program that accepts connections without its own listening socket (a proxy or security filter) would have made a
  free port look busy. Its owner lookup also read netstat's text, including non-LISTENING rows. There is no lock file
  anywhere in the script; TIME_WAIT was never counted by the connect test either.

## Decision
- A port is busy **only if the operating system lists a LISTENING socket on it**. On Windows the listener table is
  read directly with `GetExtendedTcpTable(..., TCP_TABLE_OWNER_PID_LISTENER)` through `ctypes` (standard library);
  this table class contains only listeners, so its unreliable state field is ignored. IPv4 and IPv6, any local
  address. Nothing is connected to or bound to decide. Linux: `/proc/net/tcp{,6}` rows in state LISTEN.
- Each busy port is printed with **every holder: program name and PID and the address** (name from
  `QueryFullProcessImageNameW`, falling back to `tasklist`), e.g.
  `[busy] Port 8000 is in use: something is LISTENING on it: python.exe (PID 3680) on 127.0.0.1.`
- A port inside a Windows **excluded port range** (`netsh interface ipv4|ipv6 show excludedportrange protocol=tcp`;
  on this laptop 27339 and 50000-50059) is reported separately as `[reserved]`: no program can listen there.
- If the listener table cannot be read, the script says so and does not block the start.
- **`start-dev.bat --force-ports`** skips the check and says so (`[skipped] ... were NOT checked`); a server whose port
  is really taken then stops with its own error in its window. Flags may now come in any order
  (`--dry-run`, `--no-browser`, `--force-ports`). Nothing is ever stopped by the script.

## Checked
- Tests (`backend/tests/test_devtools.py`, Windows): a real IPv4 listener and a real IPv6 listener are reported with
  this test's own PID and the program name, and are still listening afterwards; free ports are free; a port left in
  TIME_WAIT is free; a successful connect alone (patched) no longer makes a free port busy; the report names every
  holder and reserved ranges; netsh output is parsed; `start-dev.bat --dry-run` prints the holder's PID, and with
  `--force-ports` prints `[skipped]` and no `[busy]`.
- By hand: a real listener on spare port 8091 → `[busy] Port 8091 ... python.exe (PID 10980) on 127.0.0.1`;
  `--force-ports` → skipped; 8091 closed again → no port problem. On the real ports 8000/5173/5174 the new check named
  python.exe 3680 and node.exe 18272 / 27116.

## Incident during the check
A manual "real run with a busy spare port" started its listener with code that PowerShell's quoting broke, so the
listener exited at once. Port 8091 was therefore really free, the check correctly passed, and `start-dev.bat` started
a real LogiMind on 8091/8092/8093 with the developer's `backend\.env` and database. Its four windows were stopped by
exact process tree. **Side effect:** its start-up rotated the demo key in the shared database, so the developer's
already running LogiMind (from 20:11) now gets 401 for its in-memory demo key; restarting that LogiMind fixes it.
**Known limit (not changed here):** two LogiMind instances on different ports that share one database revoke each
other's demo key.
