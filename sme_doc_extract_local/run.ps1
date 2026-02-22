# run.ps1 – Safe Flask startup script
# Usage: powershell -ExecutionPolicy Bypass -File run.ps1

Write-Host "Stopping any existing Python processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host "Starting Flask server..." -ForegroundColor Yellow
$proc = Start-Process python -ArgumentList "app.py" -NoNewWindow -PassThru
Start-Sleep -Seconds 3

Write-Host "Running processes:" -ForegroundColor Yellow
Get-Process python | Select-Object Id, StartTime

Write-Host "Checking server health..." -ForegroundColor Yellow
try {
    $kpis = Invoke-RestMethod http://localhost:8000/api/dashboard -ErrorAction Stop
    Write-Host "Server is UP. Total emissions: $($kpis.kpis.total_emissions_tco2e) tCO2e" -ForegroundColor Green
} catch {
    Write-Host "Server did not respond: $_" -ForegroundColor Red
}

Write-Host "Flask PID: $($proc.Id) — open http://localhost:8000" -ForegroundColor Cyan
