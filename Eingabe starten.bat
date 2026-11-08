@echo off
title Laufdaten - Eingabe
cd /d "%~dp0"
python admin.py
if errorlevel 1 pause
