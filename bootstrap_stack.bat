@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0bootstrap_stack.ps1" %*
