# PowerShell install script for Walled DLP
# Run this once after loading the extension in Chrome

param(
    [Parameter(Mandatory=$true)]
    [string]$ExtensionId
)

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Walled DLP — Native Host Installer" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$nativeDir   = Join-Path $scriptDir "native_host"
$installPy   = Join-Path $nativeDir "install_host.py"

# Check Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python not found. Please install Python 3.8+ from https://python.org" -ForegroundColor Red
    exit 1
}

Write-Host "Using Python: $($python.Source)" -ForegroundColor Green
Write-Host "Extension ID: $ExtensionId" -ForegroundColor Green
Write-Host ""

# Run the Python installer
python $installPy $ExtensionId

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Installation successful!" -ForegroundColor Green
    Write-Host "Please restart Chrome if it is currently open." -ForegroundColor Yellow
} else {
    Write-Host "Installation failed. See errors above." -ForegroundColor Red
    exit 1
}
