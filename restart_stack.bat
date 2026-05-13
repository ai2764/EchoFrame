@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0restart_stack.ps1" %*
