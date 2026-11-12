@echo off
rem LogiMind public demo from this PC (decision 0039). Starts, each in its own window:
rem   1. the API: npm run dev in backend\ (reads backend\.env, solves plans in the same process)
rem   2. a free Cloudflare quick tunnel to http://localhost:8000
rem and prints the tunnel address. If it changed, put it in Vercel as VITE_API_URL and redeploy.
rem backend\.env needs LOGIMIND_DEMO_MODE=1, LOGIMIND_PUBLIC_DEMO=1 and FRONTEND_URL=https://logi-mind-ten.vercel.app
rem Anything already running (a backend on port 8000, or cloudflared) is kept, not started twice.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

findstr /b /c:"LOGIMIND_DEMO_MODE=1" backend\.env >nul 2>&1 || echo [warning] backend\.env: LOGIMIND_DEMO_MODE=1 is missing
findstr /b /c:"LOGIMIND_PUBLIC_DEMO=1" backend\.env >nul 2>&1 || echo [warning] backend\.env: LOGIMIND_PUBLIC_DEMO=1 is missing
findstr /b /c:"FRONTEND_URL=https" backend\.env >nul 2>&1 || echo [warning] backend\.env: FRONTEND_URL=https://... is missing

set "CF="
for /f "delims=" %%P in ('where cloudflared 2^>nul') do if not defined CF set "CF=%%P"
if not defined CF if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not defined CF if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
if not defined CF (echo [error] cloudflared not found. Install it with: winget install Cloudflare.cloudflared & exit /b 1)

rem ---- 1. API -----------------------------------------------------------------------------------------------------
rem netstat, not Get-NetTCPConnection: on this laptop the latter sometimes misses uvicorn's listener (12 Nov 2026).
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if not errorlevel 1 (
  echo [api] A program already listens on port 8000; not starting a second backend.
) else (
  echo [api] Starting the backend in the window "LogiMind API (demo)"...
  start "LogiMind API (demo)" /d "%~dp0backend" cmd /k npm run dev
)

rem ---- 2. Tunnel --------------------------------------------------------------------------------------------------
tasklist /fi "imagename eq cloudflared.exe" | find /i "cloudflared.exe" >nul
if not errorlevel 1 (
  echo [tunnel] cloudflared is already running; keeping it, so its address stays the same.
) else (
  echo [tunnel] Starting the tunnel in the window "LogiMind tunnel"...
  start "LogiMind tunnel" "%CF%" tunnel --url http://localhost:8000
)

rem ---- 3. Wait for both and print the address ---------------------------------------------------------------------
rem cloudflared reports a quick tunnel's host name on its local metrics port (127.0.0.1:20241, or up to 20245).
set "URL="
for /l %%i in (1,1,60) do if not defined URL (
  for /f "delims=" %%U in ('powershell -NoProfile -Command "foreach ($p in 20241..20245) { try { $h = (Invoke-RestMethod -TimeoutSec 2 ('http://127.0.0.1:' + $p + '/quicktunnel')).hostname; if ($h) { 'https://' + $h; break } } catch {} }"') do set "URL=%%U"
  if not defined URL ping -n 2 127.0.0.1 >nul
)
set "API="
for /l %%i in (1,1,90) do if not defined API (
  powershell -NoProfile -Command "try { $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8000/health; exit 0 } catch { exit 1 }" && set "API=1"
  if not defined API ping -n 2 127.0.0.1 >nul
)
echo.
if defined API (echo [api] Backend answers on http://localhost:8000) else echo [api] Backend not answering yet; look at its window.
if defined URL (
  echo Tunnel address: !URL!
  echo If this differs from Vercel's VITE_API_URL, set VITE_API_URL=!URL! in Vercel ^(Settings, Environment Variables^) and Redeploy.
) else (
  echo [tunnel] Address not found. Read it in the cloudflared window: the line with https://....trycloudflare.com
)
echo Keep both windows open while the demo is in use.
endlocal
