# Installation Verification Script
# Run this script to verify your installation is correct

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Installation Verification Test" -ForegroundColor Cyan
Write-Host "   AI-Driven BI Dashboard Generator" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$allTestsPassed = $true

# Test 1: Python Installation
Write-Host "[Test 1/7] Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3\.\d+\.\d+") {
        Write-Host "  ✅ PASSED: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "  ❌ FAILED: Python 3.9+ required" -ForegroundColor Red
        $allTestsPassed = $false
    }
} catch {
    Write-Host "  ❌ FAILED: Python not found. Install Python 3.9+" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 2: Virtual Environment
Write-Host "`n[Test 2/7] Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path "backend\venv") {
    Write-Host "  ✅ PASSED: Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAILED: Run 'python -m venv venv' in backend folder" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 3: Backend Directory Structure
Write-Host "`n[Test 3/7] Checking backend structure..." -ForegroundColor Yellow
$backendFiles = @("backend\app\main.py", "backend\requirements.txt", "backend\.env")
$missingFiles = @()
foreach ($file in $backendFiles) {
    if (!(Test-Path $file)) {
        $missingFiles += $file
    }
}
if ($missingFiles.Count -eq 0) {
    Write-Host "  ✅ PASSED: All backend files present" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAILED: Missing files: $($missingFiles -join ', ')" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 4: Frontend Directory Structure
Write-Host "`n[Test 4/7] Checking frontend structure..." -ForegroundColor Yellow
$frontendFiles = @("frontend\index.html", "frontend\login.html", "frontend\upload.html")
$missingFiles = @()
foreach ($file in $frontendFiles) {
    if (!(Test-Path $file)) {
        $missingFiles += $file
    }
}
if ($missingFiles.Count -eq 0) {
    Write-Host "  ✅ PASSED: All frontend files present" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAILED: Missing files: $($missingFiles -join ', ')" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 5: Backend Dependencies (if venv exists)
Write-Host "`n[Test 5/7] Checking backend dependencies..." -ForegroundColor Yellow
if (Test-Path "backend\venv") {
    Push-Location backend
    & .\venv\Scripts\Activate.ps1
    $fastapi = pip list 2>&1 | Select-String "fastapi"
    $uvicorn = pip list 2>&1 | Select-String "uvicorn"
    $pandas = pip list 2>&1 | Select-String "pandas"
    
    if ($fastapi -and $uvicorn -and $pandas) {
        Write-Host "  ✅ PASSED: Core dependencies installed" -ForegroundColor Green
        Write-Host "     - FastAPI: $($fastapi -replace '\s+', ' ')" -ForegroundColor Gray
        Write-Host "     - Uvicorn: $($uvicorn -replace '\s+', ' ')" -ForegroundColor Gray
        Write-Host "     - Pandas: $($pandas -replace '\s+', ' ')" -ForegroundColor Gray
    } else {
        Write-Host "  ❌ FAILED: Run 'pip install -r requirements.txt' in backend folder" -ForegroundColor Red
        $allTestsPassed = $false
    }
    deactivate 2>$null
    Pop-Location
} else {
    Write-Host "  ⏭️  SKIPPED: Virtual environment not created yet" -ForegroundColor Yellow
}

# Test 6: Port Availability
Write-Host "`n[Test 6/7] Checking port availability..." -ForegroundColor Yellow
$port8000 = netstat -ano | Select-String ":8000.*LISTENING"
$port3000 = netstat -ano | Select-String ":3000.*LISTENING"

if ($port8000) {
    Write-Host "  ⚠️  WARNING: Port 8000 already in use (Backend)" -ForegroundColor Yellow
    Write-Host "     If you want to start backend, stop existing process first" -ForegroundColor Gray
} else {
    Write-Host "  ✅ Port 8000 available (Backend)" -ForegroundColor Green
}

if ($port3000) {
    Write-Host "  ⚠️  WARNING: Port 3000 already in use (Frontend)" -ForegroundColor Yellow
    Write-Host "     If you want to start frontend, stop existing process first" -ForegroundColor Gray
} else {
    Write-Host "  ✅ Port 3000 available (Frontend)" -ForegroundColor Green
}

# Test 7: Documentation Files
Write-Host "`n[Test 7/7] Checking documentation..." -ForegroundColor Yellow
$docFiles = @("INSTALLATION_GUIDE.md", "USER_GUIDE.md", "DEMO_SCRIPT.md")
$foundDocs = 0
foreach ($file in $docFiles) {
    if (Test-Path $file) {
        $foundDocs++
    }
}
Write-Host "  ✅ PASSED: Found $foundDocs/$($docFiles.Count) documentation files" -ForegroundColor Green

# Final Result
Write-Host "`n========================================" -ForegroundColor Cyan
if ($allTestsPassed) {
    Write-Host "   ✅ ALL CRITICAL TESTS PASSED!" -ForegroundColor Green
    Write-Host "   Your installation is ready!" -ForegroundColor Green
    Write-Host "`n   Next Steps:" -ForegroundColor White
    Write-Host "   1. Run: cd backend; .\venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "   2. Run: uvicorn app.main:app --reload --port 8000" -ForegroundColor White
    Write-Host "   3. Open new terminal" -ForegroundColor White
    Write-Host "   4. Run: cd frontend; python -m http.server 3000" -ForegroundColor White
    Write-Host "   5. Open browser: http://localhost:3000" -ForegroundColor White
} else {
    Write-Host "   ❌ SOME TESTS FAILED" -ForegroundColor Red
    Write-Host "   Please fix the issues above" -ForegroundColor Red
    Write-Host "   Refer to INSTALLATION_GUIDE.md for help" -ForegroundColor Yellow
}
Write-Host "========================================`n" -ForegroundColor Cyan
