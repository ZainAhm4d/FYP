# Startup Script - Start Both Servers
# This script starts both Backend and Frontend servers automatically

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Starting BI Dashboard Application" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if Python is installed
Write-Host "[1/4] Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✅ Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ❌ ERROR: Python not found!" -ForegroundColor Red
    Write-Host "  Please install Python 3.9+ and add to PATH" -ForegroundColor Red
    exit 1
}

# Check if virtual environment exists
Write-Host "`n[2/4] Checking virtual environment..." -ForegroundColor Yellow
if (!(Test-Path "backend\venv")) {
    Write-Host "  ❌ ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "  Please run: cd backend; python -m venv venv" -ForegroundColor Yellow
    exit 1
}
Write-Host "  ✅ Virtual environment exists" -ForegroundColor Green

# Check if dependencies are installed
Write-Host "`n[3/4] Checking dependencies..." -ForegroundColor Yellow
Push-Location backend
& .\venv\Scripts\Activate.ps1
$fastapi = pip list 2>&1 | Select-String "fastapi"
if (!$fastapi) {
    Write-Host "  ❌ ERROR: Dependencies not installed!" -ForegroundColor Red
    Write-Host "  Please run: cd backend; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt" -ForegroundColor Yellow
    Pop-Location
    exit 1
}
deactivate 2>$null
Pop-Location
Write-Host "  ✅ Dependencies installed" -ForegroundColor Green

# Start Backend Server (Background)
Write-Host "`n[4/4] Starting servers..." -ForegroundColor Yellow

Write-Host "`n  🚀 Starting Backend Server (Port 8000)..." -ForegroundColor Cyan
$backendJob = Start-Job -ScriptBlock {
    Set-Location "$using:PWD\backend"
    & .\venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}

# Wait a moment for backend to start
Start-Sleep -Seconds 3

# Start Frontend Server (Background)
Write-Host "  🌐 Starting Frontend Server (Port 3000)..." -ForegroundColor Cyan
$frontendJob = Start-Job -ScriptBlock {
    Set-Location "$using:PWD\frontend"
    python -m http.server 3000
}

# Wait a moment for frontend to start
Start-Sleep -Seconds 2

# Check if servers started successfully
Write-Host "`n========================================" -ForegroundColor Cyan

$backendRunning = netstat -ano | Select-String ":8000.*LISTENING"
$frontendRunning = netstat -ano | Select-String ":3000.*LISTENING"

if ($backendRunning) {
    Write-Host "  ✅ Backend Server: RUNNING" -ForegroundColor Green
    Write-Host "     URL: http://localhost:8000" -ForegroundColor Gray
    Write-Host "     API Docs: http://localhost:8000/docs" -ForegroundColor Gray
} else {
    Write-Host "  ❌ Backend Server: FAILED TO START" -ForegroundColor Red
}

if ($frontendRunning) {
    Write-Host "`n  ✅ Frontend Server: RUNNING" -ForegroundColor Green
    Write-Host "     URL: http://localhost:3000" -ForegroundColor Gray
} else {
    Write-Host "`n  ❌ Frontend Server: FAILED TO START" -ForegroundColor Red
}

Write-Host "`n========================================" -ForegroundColor Cyan

if ($backendRunning -and $frontendRunning) {
    Write-Host "  🎉 APPLICATION STARTED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "`n  📍 Open your browser and go to:" -ForegroundColor White
    Write-Host "     http://localhost:3000" -ForegroundColor Cyan -NoNewline
    Write-Host " ← Main Application" -ForegroundColor Gray
    Write-Host "`n  💡 Tip: Keep this window open while using the app" -ForegroundColor Yellow
    Write-Host "`n  🛑 To stop servers, run:" -ForegroundColor White
    Write-Host "     .\stop-servers.ps1" -ForegroundColor Cyan
    Write-Host "     or press CTRL+C and run: Get-Job | Stop-Job" -ForegroundColor Gray
} else {
    Write-Host "  ⚠️  Some servers failed to start" -ForegroundColor Yellow
    Write-Host "  Check if ports 8000 and 3000 are already in use" -ForegroundColor Yellow
    Write-Host "  Run: netstat -ano | findstr ':8000 :3000'" -ForegroundColor Gray
}

Write-Host "========================================`n" -ForegroundColor Cyan

# Keep the script running and show logs
Write-Host "📝 Server Logs (Press CTRL+C to stop):" -ForegroundColor Cyan
Write-Host "----------------------------------------`n" -ForegroundColor Gray

# Show job status
while ($true) {
    Start-Sleep -Seconds 5
    $jobs = Get-Job
    $allRunning = $true
    foreach ($job in $jobs) {
        if ($job.State -ne "Running") {
            $allRunning = $false
            Write-Host "`n⚠️  Warning: A server has stopped!" -ForegroundColor Yellow
            Write-Host "Job: $($job.Name) - State: $($job.State)" -ForegroundColor Red
            break
        }
    }
    if (!$allRunning) {
        break
    }
}

Write-Host "`n🛑 Servers stopped. Cleaning up..." -ForegroundColor Yellow
Get-Job | Stop-Job
Get-Job | Remove-Job
Write-Host "Cleanup complete.`n" -ForegroundColor Green
