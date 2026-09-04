# ==============================================================================
# 🚇 Cloudflare Tunnel — Instant Public HTTPS for Business AI Robot
# ==============================================================================
# Exposes http://localhost:8000 to a public HTTPS URL (e.g. https://xyz.trycloudflare.com)
# so the ESP32 can connect over the internet without configuring router ports.
# ==============================================================================

$cloudflaredPath = "$PSScriptRoot\cloudflared.exe"

# 1. Download cloudflared if not present
if (!(Test-Path $cloudflaredPath)) {
    Write-Host "📥 Downloading Cloudflare Tunnel binary (cloudflared.exe)..." -ForegroundColor Cyan
    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $cloudflaredPath
    Write-Host "✅ Download complete." -ForegroundColor Green
}

Write-Host "`n🚀 Starting Cloudflare Tunnel on http://localhost:8000..." -ForegroundColor Yellow
Write-Host "Look for the public HTTPS URL in the logs below (e.g., https://your-name.trycloudflare.com)`n" -ForegroundColor Cyan

& $cloudflaredPath tunnel --url http://localhost:8000
