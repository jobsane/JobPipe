@echo off
setlocal
cd /d "%~dp0"

REM Prefer venv python if present
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

REM Build a detailed report from the latest run per job_id.
REM --only-non-expired keeps only jobs that are not past the due date.
"%PY%" -m jobpipe.cli.sync_ledger --out ".\out_runs" --reports ".\reports" --detailed-report --only-non-expired

echo.
echo Done. See .\reports\
pause
