Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "              DUIT - Full Stack Launcher               " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

# 1. Start Shed Remote Task Plane (Port 4378)
Write-Host "[1/5] Launching Shed Remote Task Plane (Port 4378)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd E:\Inovvate\shed; node server/index.js" -WindowStyle Normal

# 2. Start FastAPI Cascade Backend (Port 8000)
Write-Host "[2/5] Launching FastAPI Cascade Backend (Port 8000)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd E:\Inovvate; python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload" -WindowStyle Normal

# 3. Start Desktop Sidecar Daemon
Write-Host "[3/5] Launching Desktop Sidecar Daemon..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd E:\Inovvate; python desktop/sidecar/runner.py" -WindowStyle Normal

# 4. Start Cloudflare Tunnel (Port 5122)
Write-Host "[4/5] Launching Cloudflare Tunnel (Port 5122)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd E:\Inovvate; .\cloudflared.exe tunnel --url http://localhost:5122" -WindowStyle Normal

# 5. Start WhatsApp Bot Gateway (Port 5122)
Write-Host "[5/5] Launching WhatsApp Bot Gateway (Port 5122)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd E:\Inovvate\whatsapp\directorbot; node server.js" -WindowStyle Normal

Write-Host "=======================================================" -ForegroundColor Green
Write-Host "All 5 services launched in dedicated PowerShell windows." -ForegroundColor Green
Write-Host "- Shed Task Plane:   http://localhost:4378" -ForegroundColor Green
Write-Host "- FastAPI Backend:   http://localhost:8000" -ForegroundColor Green
Write-Host "- WhatsApp Gateway:  http://localhost:5122" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
