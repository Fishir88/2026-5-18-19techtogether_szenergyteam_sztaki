# Real2Sim Setup Script for Windows PowerShell
# Usage: .\setup.ps1

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginDir = Join-Path $scriptRoot "openclaw-real2sim-plugin"
$openclawConfigDir = Join-Path $env:USERPROFILE ".openclaw"
$openclawConfigPath = Join-Path $openclawConfigDir "openclaw.json"

function Get-OrCreateObjectProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$InputObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    $property = $InputObject.PSObject.Properties[$PropertyName]
    if ($null -eq $property) {
        $newObject = [pscustomobject]@{}
        $InputObject | Add-Member -NotePropertyName $PropertyName -NotePropertyValue $newObject
        return $newObject
    }

    return $property.Value
}

Write-Host "========== Real2Sim Setup ==========" -ForegroundColor Cyan
Write-Host "This script will:" -ForegroundColor Yellow
Write-Host "  1. Remove old venv directories" -ForegroundColor Gray
Write-Host "  2. Create Python 3.12 virtual environment" -ForegroundColor Gray
Write-Host "  3. Install Python dependencies" -ForegroundColor Gray
Write-Host "  4. Install OpenClaw plugin dependencies" -ForegroundColor Gray
Write-Host "  5. Configure OpenClaw if it is installed" -ForegroundColor Gray
Write-Host ""

# Check Python 3.12 availability
Write-Host "[1/4] Checking Python 3.12..." -ForegroundColor Cyan
$python312 = py -3.12 --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Found: $python312" -ForegroundColor Green
} else {
    Write-Host "✗ Python 3.12 not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.12 from python.org" -ForegroundColor Yellow
    exit 1
}

# Remove old venvs
Write-Host "[2/4] Cleaning up old environments..." -ForegroundColor Cyan
if (Test-Path .\venv) {
    Write-Host "  Removing venv/" -ForegroundColor Gray
    Remove-Item -Recurse -Force .\venv
}
if (Test-Path .\venv312) {
    Write-Host "  Removing venv312/" -ForegroundColor Gray
    Remove-Item -Recurse -Force .\venv312
}
Write-Host "✓ Cleanup complete" -ForegroundColor Green

# Create venv
Write-Host "[3/4] Creating virtual environment..." -ForegroundColor Cyan
py -3.12 -m venv venv
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to create virtual environment" -ForegroundColor Red
    exit 1
}

# Activate and install
Write-Host "[4/5] Installing Python dependencies..." -ForegroundColor Cyan
.\venv\Scripts\activate.ps1

Write-Host "  Upgrading pip/setuptools/wheel..." -ForegroundColor Gray
python -m pip install --quiet --upgrade pip setuptools wheel
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ pip upgraded" -ForegroundColor Green
} else {
    Write-Host "  ✗ pip upgrade failed" -ForegroundColor Yellow
}

Write-Host "  Installing requirements.txt..." -ForegroundColor Gray
pip install --quiet -r requirements.txt
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  ✗ Some dependencies failed (check log above)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[5/5] Setting up OpenClaw integration..." -ForegroundColor Cyan

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($null -ne $npm -and (Test-Path $pluginDir)) {
    Push-Location $pluginDir
    try {
        Write-Host "  Installing OpenClaw plugin dependencies..." -ForegroundColor Gray
        npm install --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ OpenClaw plugin dependencies installed" -ForegroundColor Green
        } else {
            Write-Host "  ✗ OpenClaw plugin dependency install failed" -ForegroundColor Yellow
        }
    } finally {
        Pop-Location
    }
} elseif ($null -eq $npm) {
    Write-Host "  ✗ npm not found; skipping OpenClaw plugin dependency install" -ForegroundColor Yellow
} else {
    Write-Host "  ✗ OpenClaw plugin directory not found; skipping plugin dependency install" -ForegroundColor Yellow
}

$openclaw = Get-Command openclaw -ErrorAction SilentlyContinue
if ($null -eq $openclaw) {
    Write-Host "  OpenClaw is not installed; skipping OpenClaw config setup" -ForegroundColor Yellow
} else {
    Write-Host "  OpenClaw found; merging local plugin config" -ForegroundColor Gray
    if (-not (Test-Path $openclawConfigDir)) {
        New-Item -ItemType Directory -Force -Path $openclawConfigDir | Out-Null
    }

    $config = if (Test-Path $openclawConfigPath) {
        try {
            Get-Content $openclawConfigPath -Raw | ConvertFrom-Json -Depth 20
        } catch {
            Write-Host "  Existing OpenClaw config is invalid JSON; rebuilding from a minimal base" -ForegroundColor Yellow
            [pscustomobject]@{}
        }
    } else {
        [pscustomobject]@{}
    }

    $plugins = Get-OrCreateObjectProperty -InputObject $config -PropertyName "plugins"
    $entries = Get-OrCreateObjectProperty -InputObject $plugins -PropertyName "entries"
    $entries | Add-Member -NotePropertyName "real2sim" -NotePropertyValue ([pscustomobject]@{
        path = $pluginDir
        enabled = $true
        config = [pscustomobject]@{
            apiBaseUrl = "http://127.0.0.1:8765"
        }
    }) -Force

    $tools = Get-OrCreateObjectProperty -InputObject $config -PropertyName "tools"
    $allowedTools = @()
    if ($null -ne $tools.PSObject.Properties["allow"]) {
        $allowedTools = @($tools.allow)
    }

    foreach ($toolName in @("real2sim_state", "real2sim_command")) {
        if ($allowedTools -notcontains $toolName) {
            $allowedTools += $toolName
        }
    }

    $tools | Add-Member -NotePropertyName "allow" -NotePropertyValue $allowedTools -Force
    $config | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $openclawConfigPath
    Write-Host "  ✓ OpenClaw config written to $openclawConfigPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "========== Setup Complete ==========" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Make sure you're in the venv:"
Write-Host "     .\venv\Scripts\activate"
Write-Host ""
Write-Host "  2. Run the Real2Sim system:"
Write-Host "     .\run_real2sim.ps1           # Full system with MuJoCo"
Write-Host "     .\venv\Scripts\python.exe pose_test.py     # Pose detection only"
Write-Host "     .\venv\Scripts\python.exe g1_controller.py  # G1 test (no camera)"
Write-Host ""
Write-Host "  3. OpenClaw integration:" 
Write-Host "     If OpenClaw is installed, the local plugin entry has been merged into"
Write-Host "     %USERPROFILE%\.openclaw\openclaw.json"
Write-Host ""
Write-Host "  4. View documentation:" 
Write-Host "     notepad OPENCLAW_INTEGRATION.md"
Write-Host ""
