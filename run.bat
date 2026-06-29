@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0"
set "VENV=%PROJECT_ROOT%.venv"

if not exist "%VENV%\Scripts\python.exe" (
  echo Creating Python virtual environment...
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv "%VENV%" || goto :error
  ) else (
    py -3 -m venv "%VENV%" || goto :error
  )
)

echo Installing requirements...
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%PROJECT_ROOT%requirements.txt" || goto :error

set "PYTHON_EXE=%VENV%\Scripts\python.exe"
call "%PROJECT_ROOT%run-java.bat" %*
exit /b %errorlevel%

:error
echo.
echo Unable to prepare or start the project.
pause
exit /b 1
