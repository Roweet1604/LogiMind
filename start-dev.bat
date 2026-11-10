@echo off
rem LogiMind on this computer (Windows), decisions 0028-0030. Double-click it, or run:
rem   start-dev.bat                                   set up what is missing, start everything, open the console
rem   start-dev.bat --dry-run                         show what would happen; change and start nothing
rem   start-dev.bat --no-browser                      start everything but do not open the browser
rem   start-dev.bat tenant "Acme Fleet"               create a tenant; prints its API key ONCE
rem First run (once): makes the Python environment in %TEMP%\lmv, installs the backend packages, writes
rem backend\.env with a new driver-link secret, and runs npm install in frontend\ and driver\ (npm runs nowhere else).
rem Settings: backend\.env (git-ignored). Variables already set in this window win.
rem Ports: API_PORT (8000), CONSOLE_PORT (5173), DRIVER_PORT (5174). Python: LOGIMIND_PYTHON, else %TEMP%\lmv.
rem Demo mode is on here (local only, synthetic data); set LOGIMIND_DEMO_MODE=0 in backend\.env to turn it off.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"
set "DRY="
set "BROWSER=1"
if /i "%~1"=="--dry-run" set "DRY=1"
if /i "%~1"=="--no-browser" set "BROWSER="
if not exist "%TEMP%" (echo [error] The TEMP folder is not set. & exit /b 1)

rem ---- 1. Python environment (one time) --------------------------------------------------------------------------
set "OWN_PYTHON="
if defined LOGIMIND_PYTHON set "OWN_PYTHON=1"
if not defined LOGIMIND_PYTHON set "LOGIMIND_PYTHON=%TEMP%\lmv\Scripts\python.exe"
if not exist "%LOGIMIND_PYTHON%" (
  if defined OWN_PYTHON (
    echo [error] LOGIMIND_PYTHON points to %LOGIMIND_PYTHON%, which does not exist.
    exit /b 1
  )
  call :find_base_python || exit /b 1
  echo [setup] Creating the Python environment in %TEMP%\lmv ^(one time^) with !BASE_PY!
  if defined DRY (echo [dry-run] !BASE_PY! -m venv "%TEMP%\lmv") else (
    !BASE_PY! -m venv "%TEMP%\lmv" || (echo [error] Could not create the Python environment. & exit /b 1)
  )
)
rem The check imports names, not just packages: a half-deleted package folder still imports as an empty namespace,
rem and pip still calls it installed. Seen on 10 Nov 2026: most .py files in %TEMP%\lmv vanished (decision 0030).
set "NEED_PIP="
set "PIP_MODE="
if exist "%LOGIMIND_PYTHON%" (
  "%LOGIMIND_PYTHON%" -c "from fastapi import FastAPI; from uvicorn import run; from ortools.constraint_solver import pywrapcp; from sqlalchemy import select; from alembic import command; from langgraph.graph import StateGraph" >nul 2>&1 || set "NEED_PIP=1"
) else set "NEED_PIP=1"
if defined NEED_PIP if exist "%LOGIMIND_PYTHON%" (
  "%LOGIMIND_PYTHON%" -m pip show fastapi >nul 2>&1 && set "PIP_MODE=--force-reinstall"
)
if defined NEED_PIP (
  if defined PIP_MODE (echo [setup] The Python packages look damaged: reinstalling them...) else (
    echo [setup] Installing the backend packages ^(one time; can take 10 minutes or more on a slow connection^)...
  )
  if defined DRY (echo [dry-run] "%LOGIMIND_PYTHON%" -m pip install !PIP_MODE! -r backend\requirements.txt) else (
    "%LOGIMIND_PYTHON%" -m pip install --disable-pip-version-check !PIP_MODE! -r "%ROOT%\backend\requirements.txt"
    if errorlevel 1 (
      echo [error] pip install failed; the reason is printed above. If it keeps failing, delete the folder
      echo         %TEMP%\lmv and run start-dev.bat again.
      exit /b 1
    )
  )
)

rem ---- 2. backend\.env with a driver-link secret (one time; existing values are never changed) -------------------
if defined DRY (
  if not exist "backend\.env" echo [dry-run] would create backend\.env with a new LOGIMIND_DRIVER_LINK_SECRET
) else (
  "%LOGIMIND_PYTHON%" "%ROOT%\backend\scripts\devtools.py" env || exit /b 1
)
if exist "backend\.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("backend\.env") do (
    if not "%%B"=="" if not defined %%A set "%%A=%%B"
  )
)

rem ---- tenant mode -----------------------------------------------------------------------------------------------
if /i "%~1"=="tenant" (
  if "%~2"=="" (
    echo usage: start-dev.bat tenant "Tenant name"
    exit /b 2
  )
  pushd backend
  "%LOGIMIND_PYTHON%" manage.py create-tenant "%~2"
  set "RC=!errorlevel!"
  popd
  exit /b !RC!
)

rem ---- 3. Node packages for the console and the driver app (one time) -------------------------------------------
where npm >nul 2>&1 || (
  echo [error] Node.js is not installed ^(npm not found^). Install the LTS version from nodejs.org, then run this again.
  exit /b 1
)
for %%D in (frontend driver) do (
  if not exist "%ROOT%\%%D\node_modules" (
    echo [setup] npm install in %%D\ ^(one time^)...
    if defined DRY (echo [dry-run] npm install in %%D) else (
      pushd "%ROOT%\%%D"
      call npm install --no-audit --no-fund
      set "RC=!errorlevel!"
      popd
      if not "!RC!"=="0" (echo [error] npm install failed in %%D\; the reason is printed above. & exit /b 1)
    )
  )
)

rem ---- 4. Ports: report what is busy; never stop anything --------------------------------------------------------
if not defined API_PORT set "API_PORT=8000"
if not defined CONSOLE_PORT set "CONSOLE_PORT=5173"
if not defined DRIVER_PORT set "DRIVER_PORT=5174"
if exist "%LOGIMIND_PYTHON%" (
  "%LOGIMIND_PYTHON%" "%ROOT%\backend\scripts\devtools.py" ports %API_PORT% %CONSOLE_PORT% %DRIVER_PORT%
  if errorlevel 1 if not defined DRY exit /b 1
)

rem ---- 5. Start the four windows ---------------------------------------------------------------------------------
rem A separate worker window runs the solver jobs, so the API only queues them.
set "LOGIMIND_WORKER=external"
rem Demo mode (decision 0029): demo tenant with synthetic plans; the console signs in by itself. Local only:
rem the API listens on 127.0.0.1 and the backend refuses demo mode for any other bind host.
if not defined LOGIMIND_DEMO_MODE set "LOGIMIND_DEMO_MODE=1"
set "LOGIMIND_BIND_HOST=127.0.0.1"
if not defined LOGIMIND_DRIVER_APP_URL set "LOGIMIND_DRIVER_APP_URL=http://localhost:%DRIVER_PORT%"
rem 127.0.0.1, not localhost: the API listens on IPv4 loopback only.
set "VITE_BACKEND_URL=http://127.0.0.1:%API_PORT%"
set "LAUNCH=start"
if defined DRY set "LAUNCH=echo [dry-run] start"
%LAUNCH% "LogiMind API :%API_PORT%" /d "%ROOT%\backend" cmd /k ""%LOGIMIND_PYTHON%" -m uvicorn app.main:app --reload --host %LOGIMIND_BIND_HOST% --port %API_PORT%"
%LAUNCH% "LogiMind worker" /d "%ROOT%\backend" cmd /k ""%LOGIMIND_PYTHON%" -m app.jobs.worker"
%LAUNCH% "LogiMind console :%CONSOLE_PORT%" /d "%ROOT%\frontend" cmd /k "npm run dev -- --port %CONSOLE_PORT% --strictPort"
%LAUNCH% "LogiMind driver :%DRIVER_PORT%" /d "%ROOT%\driver" cmd /k "npm run dev -- --port %DRIVER_PORT% --strictPort"
if defined DRY (echo [dry-run] would wait for the API and the console, then open http://localhost:%CONSOLE_PORT%/ & exit /b 0)

rem ---- 6. Wait until the API and the console answer, then open the console ---------------------------------------
echo Waiting for the API on port %API_PORT% ...
"%LOGIMIND_PYTHON%" "%ROOT%\backend\scripts\devtools.py" wait http://127.0.0.1:%API_PORT%/api/health 180 || exit /b 1
echo Waiting for the console on port %CONSOLE_PORT% ...
"%LOGIMIND_PYTHON%" "%ROOT%\backend\scripts\devtools.py" wait http://localhost:%CONSOLE_PORT%/ 120 || exit /b 1
if defined BROWSER start "" "http://localhost:%CONSOLE_PORT%/plans"

echo.
echo   LogiMind is running.
echo   Console  http://localhost:%CONSOLE_PORT%/plans   (demo mode: signs in to "Demo Fleet (synthetic)" by itself)
echo   Driver   http://localhost:%DRIVER_PORT%          (open a link made on a plan's Drivers panel)
echo   API      http://127.0.0.1:%API_PORT%/docs
echo   Stop: close the four "LogiMind" windows (or Ctrl+C in each).
endlocal
exit /b 0

:find_base_python
set "BASE_PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set "BASE_PY=py -3"
if not defined BASE_PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set "BASE_PY=python"
if not defined BASE_PY (
  echo [error] Python 3.12 or newer was not found. Install it from python.org ^(tick "Add to PATH"^), then run this again.
  exit /b 1
)
exit /b 0
