@echo off
setlocal
if "%~1"=="" (
  echo Usage: run_poc.bat update.img
  exit /b 2
)
python poc.py all "%~1" -o poc-out
