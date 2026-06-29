@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
set "HOST=127.0.0.1"
set "PORT="
set "OPEN_BROWSER=1"

if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"

echo Agent Protocol Lab
echo Cartella progetto: %PROJECT_ROOT%
echo.

if exist "%PROJECT_ROOT%index.html" (
  rem ok
) else (
  echo index.html non trovato nella cartella del progetto.
  pause
  exit /b 1
)

if not defined PYTHON_EXE if not defined PYTHON_CMD (
  where python >nul 2>nul
  if !errorlevel!==0 (
    set "PYTHON_CMD=python"
  ) else (
    where py >nul 2>nul
    if !errorlevel!==0 (
      set "PYTHON_CMD=py -3"
    )
  )
)

if not defined PYTHON_EXE if not defined PYTHON_CMD (
  echo Python non trovato.
  echo Installa Python 3 oppure aggiungilo al PATH, poi rilancia questo file.
  pause
  exit /b 1
)

for %%P in (8000 8001 8002 8003 8004 8005 8010 8020 8030 8040) do (
  if not defined PORT (
    netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul 2>nul
    if errorlevel 1 set "PORT=%%P"
  )
)

if "%PORT%"=="" (
  echo Nessuna porta libera trovata tra 8000 e 8040.
  pause
  exit /b 1
)

set "URL=http://%HOST%:%PORT%/"
echo Avvio server locale su %URL%
echo Chiudi questa finestra per fermare il server.
echo.

pushd "%PROJECT_ROOT%" || (
  echo Impossibile entrare nella cartella progetto.
  pause
  exit /b 1
)

if "%OPEN_BROWSER%"=="1" (
  start "" "%URL%"
) else (
  echo Apri manualmente: %URL%
)

if defined PYTHON_EXE (
  "%PYTHON_EXE%" -m uvicorn agent_runtime.server:app --host %HOST% --port %PORT%
) else (
  %PYTHON_CMD% -m uvicorn agent_runtime.server:app --host %HOST% --port %PORT%
)
set "SERVER_EXIT=%ERRORLEVEL%"
popd
exit /b %SERVER_EXIT%
