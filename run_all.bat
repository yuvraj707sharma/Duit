@echo off
title DUIT Complete Stack Launcher
echo =======================================================
echo              DUIT - Full Stack Launcher               
echo =======================================================

echo [1/5] Launching Shed Remote Task Plane (Port 4378)...
start "DUIT - Shed Server" cmd /k "cd /d E:\Inovvate\shed && node server/index.js"

echo [2/5] Launching FastAPI Cascade Backend (Port 8000)...
start "DUIT - Backend API" cmd /k "cd /d E:\Inovvate && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [3/5] Launching Desktop Sidecar Daemon...
start "DUIT - Desktop Sidecar" cmd /k "cd /d E:\Inovvate && python desktop/sidecar/runner.py"

echo [4/5] Launching Cloudflare Tunnel (Port 5122)...
start "DUIT - Cloudflare Tunnel" cmd /k "cd /d E:\Inovvate && cloudflared.exe tunnel --url http://localhost:5122"

echo [5/5] Launching WhatsApp Bot Gateway (Port 5122)...
start "DUIT - WhatsApp Gateway" cmd /k "cd /d E:\Inovvate\whatsapp\directorbot && node server.js"

echo =======================================================
echo All services launched in dedicated foreground windows.
echo - Shed Task Plane:   http://localhost:4378
echo - FastAPI Backend:   http://localhost:8000
echo - WhatsApp Gateway:  http://localhost:5122
echo =======================================================
pause
