@echo off
rem LogiMind local development (Windows). Opens one window each: API, worker, ops console, driver app.
rem   start-dev.bat                                   start everything
rem   start-dev.bat --dry-run                         show what would start; start nothing
rem   start-dev.bat tenant "Demo Fleet (synthetic)"   create a test tenant; prints its API key ONCE
rem Settings: backend\.env (git-ignored; copy backend\.env.example). Variables already set in this window win.
rem Ports: API_PORT (8000), CONSOLE_PORT (5173), DRIVER_PORT (5174). Python: LOGIMIND_PYTHON, else %TEMP%\lmv.
rem The backend runs with Python directly; npm runs only inside frontend\ and driver\.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"

rem ---- backend\.env: KEY=VALUE lines, # comments; empty values are skipped --------------------------------------
if exist "backend\.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("backend\.env") do (
    if not "%%B"=="" if not defined %%A set "%%A=%%B"
  )
) else (
  echo [note] backend\.env not found: using defaults. Copy backend\.env.example to backend\.env to change them.
)

rem ---- Python environment ----------------------------------------------------------------------------------------
if not defined LOGIMIND_PYTHON set "LOGIMIND_PYTHON=%TEMP%\lmv\Scripts\python.exe"
if not exist "%LOGIMIND_PYTHON%" (
  echo [error] Python not found at %LOGIMIND_PYTHON%
  echo         One-time setup:  python -m venv %%TEMP%%\lmv
  echo                          %%TEMP%%\lmv\Scripts\python -m pip install -r backend\requirements.txt
  echo         Or set LOGIMIND_PYTHON to the full path of python.exe in your environment.
  exit /b 1
)
"%LOGIMIND_PYTHON%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [error] %LOGIMIND_PYTHON% cannot import fastapi/uvicorn. Run:
  echo         "%LOGIMIND_PYTHON%" -m pip install -r backend\requirements.txt
  exit /b 1
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

if not defined API_PORT set "API_PORT=8000"
if not defined CONSOLE_PORT set "CONSOLE_PORT=5173"
if not defined DRIVER_PORT set "DRIVER_PORT=5174"
set "LAUNCH=start"
if /i "%~1"=="--dry-run" set "LAUNCH=echo start"

rem ---- refuse to start twice: on Windows a second server on the same port does not fail, and requests can go to
rem      the old one. Stop the old windows first (or pick other ports).
set "BUSY="
for %%P in (%API_PORT% %CONSOLE_PORT% %DRIVER_PORT%) do (
  netstat -ano | findstr /r /c:":%%P  *[^ ]*  *LISTENING" >nul && set "BUSY=!BUSY! %%P"
)
if defined BUSY (
  echo [error] Port^(s^)!BUSY! already in use. Close the old LogiMind windows first, or set API_PORT / CONSOLE_PORT / DRIVER_PORT.
  if /i not "%~1"=="--dry-run" exit /b 1
)
if not exist "%TEMP%" (echo [error] TEMP is not set & exit /b 1)

rem ---- environment shared by the windows -------------------------------------------------------------------------
rem A separate worker window runs the solver jobs, so the API only queues them.
set "LOGIMIND_WORKER=external"
if not defined LOGIMIND_DRIVER_APP_URL set "LOGIMIND_DRIVER_APP_URL=http://localhost:%DRIVER_PORT%"
set "VITE_BACKEND_URL=http://localhost:%API_PORT%"
if not defined LOGIMIND_DRIVER_LINK_SECRET echo [note] LOGIMIND_DRIVER_LINK_SECRET is not set: driver links stop working when the API restarts.

%LAUNCH% "LogiMind API :%API_PORT%" /d "%ROOT%\backend" cmd /k ""%LOGIMIND_PYTHON%" -m uvicorn app.main:app --reload --port %API_PORT%"
%LAUNCH% "LogiMind worker" /d "%ROOT%\backend" cmd /k ""%LOGIMIND_PYTHON%" -m app.jobs.worker"
rem npm install runs first only where node_modules is missing (decided here: an "if ... &" inside cmd /k did not run).
set "FE_CMD=npm run dev -- --port %CONSOLE_PORT% --strictPort"
if not exist "%ROOT%\frontend\node_modules" set "FE_CMD=npm install && %FE_CMD%"
set "DR_CMD=npm run dev -- --port %DRIVER_PORT% --strictPort"
if not exist "%ROOT%\driver\node_modules" set "DR_CMD=npm install && %DR_CMD%"
%LAUNCH% "LogiMind console :%CONSOLE_PORT%" /d "%ROOT%\frontend" cmd /k "%FE_CMD%"
%LAUNCH% "LogiMind driver :%DRIVER_PORT%" /d "%ROOT%\driver" cmd /k "%DR_CMD%"

echo.
echo   API      http://localhost:%API_PORT%/docs
echo   Console  http://localhost:%CONSOLE_PORT%/login   (sign in with a key from: start-dev.bat tenant "Name")
echo   Driver   http://localhost:%DRIVER_PORT%          (open a link made on a plan's Drivers panel)
echo   Stop: close the four "LogiMind" windows (or Ctrl+C in each).
endlocal
