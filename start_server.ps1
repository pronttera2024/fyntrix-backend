# ARISE Backend Server Startup Script with NEW OpenAI API Key
# Ensures environment variables are set before starting uvicorn

Write-Host "🚀 Starting ARISE Backend Server..." -ForegroundColor Cyan
Write-Host ""

# Set OpenAI API Key (from environment variable)
if (-not $env:OPENAI_API_KEY) {
    Write-Host "[WARN] OPENAI_API_KEY environment variable not set" -ForegroundColor Yellow
} else {
    Write-Host "[OK] OpenAI API Key configured from environment" -ForegroundColor Green
}
$env:OPENAI_DAILY_BUDGET = "10.0"
$env:OPENAI_MAX_RPM = "60"

# Set Zerodha API Credentials
$env:ZERODHA_API_KEY = "wialyvtiwscm10th"
$env:ZERODHA_API_SECRET = "2f1k69xaf2ju3aksepmt5fzdfrvy9mi1"

Write-Host "[OK] OpenAI API Key configured" -ForegroundColor Green
Write-Host "[OK] Zerodha API configured (Key: $($env:ZERODHA_API_KEY.Substring(0,10))...)" -ForegroundColor Green
Write-Host "[OK] Starting server on http://127.0.0.1:8010" -ForegroundColor Green  
Write-Host "[OK] AI-Powered Insights + Real-Time Data ENABLED" -ForegroundColor Cyan
Write-Host ""

# Ensure we run uvicorn from the backend folder so that the 'app' package is importable
Set-Location -Path $PSScriptRoot

# Start uvicorn on 127.0.0.1:8010 to match frontend dev proxy
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
