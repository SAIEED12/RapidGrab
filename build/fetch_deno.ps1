# Download a Deno binary so packaged builds have a JavaScript runtime for
# YouTube (yt-dlp's EJS challenge solver). Optional: skip it and RapidGrab
# will use Deno/Node/Bun installed on the machine if present.
#
# Usage: powershell -ExecutionPolicy Bypass -File build\fetch_deno.ps1

$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "deno_bin"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$zip = Join-Path $env:TEMP "rapidgrab-deno.zip"
$url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

Write-Host "Downloading Deno from $url"
Invoke-WebRequest -Uri $url -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $dest -Force
Remove-Item $zip -ErrorAction SilentlyContinue

$deno = Join-Path $dest "deno.exe"
if (-not (Test-Path $deno)) {
    throw "deno.exe was not extracted"
}

& $deno --version
Write-Host "Deno ready at $deno"
