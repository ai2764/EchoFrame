@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0kill_stack.ps1" %*
