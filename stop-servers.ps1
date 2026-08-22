# Stop Servers Script - Stops all running Backend and Frontend servers

Write-Host ""
Write-Host "========================================"
Write-Host "   Stopping BI Dashboard Servers"
Write-Host "========================================"
Write-Host ""

# Stop all background jobs
Write-Host "[1/3] Stopping background jobs..."
$jobs = Get-Job
if ($jobs.Count -gt 0) {
    Write-Host "  Found $($jobs.Count) background job(s)"
    Get-Job | Stop-Job
    Get-Job | Remove-Job
    Write-Host "  OK: All jobs stopped"
} else {
    Write-Host "  INFO: No background jobs found"
}

# Find and kill processes on port 8000 (Backend)
Write-Host ""
Write-Host "[2/3] Checking port 8000 (Backend)..."
$port8000 = netstat -ano | Select-String ":8000.*LISTENING"
if ($port8000) {
    Write-Host "  Found process(es) on port 8000:"
    $port8000 | ForEach-Object {
        $line = $_.ToString().Trim()
        $pid = ($line -split '\s+')[-1]
        Write-Host "    PID: $pid"
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "    OK: Stopped process $pid"
        } catch {
            Write-Host "    WARNING: Could not stop process $pid"
        }
    }
} else {
    Write-Host "  OK: No process on port 8000"
}

# Find and kill  processes on port 3000 (Frontend)
Write-Host ""
Write-Host "[3/3] Checking port 3000 (Frontend)..."
$port3000 = netstat -ano | Select-String ":3000.*LISTENING"
if ($port3000) {
    Write-Host "  Found process(es) on port 3000:"
    $port3000 | ForEach-Object {
        $line = $_.ToString().Trim()
        $pid = ($line -split '\s+')[-1]
        Write-Host "    PID: $pid"
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "    OK: Stopped process $pid"
        } catch {
            Write-Host "    WARNING: Could not stop process $pid"
        }
    }
} else {
    Write-Host "  OK: No process on port 3000"
}

# Final verification
Write-Host ""
Write-Host "========================================"
Start-Sleep -Seconds 1

$stillRunning8000 = netstat -ano | Select-String ":8000.*LISTENING"
$stillRunning3000 = netstat -ano | Select-String ":3000.*LISTENING"

if (!$stillRunning8000 -and !$stillRunning3000) {
    Write-Host "  SUCCESS: ALL SERVERS STOPPED!"
    Write-Host ""
    Write-Host "  Both ports (8000, 3000) are now free"
    Write-Host "  You can start the servers again with:"
    Write-Host "    .\start-servers.ps1"
} else {
    Write-Host "  WARNING: Some processes may still be running"
    if ($stillRunning8000) {
        Write-Host "  Port 8000 still in use"
    }
    if ($stillRunning3000) {
        Write-Host "  Port 3000 still in use"
    }
    Write-Host ""
    Write-Host "  Try running this script again or restart your computer"
}

Write-Host "========================================"
Write-Host ""
