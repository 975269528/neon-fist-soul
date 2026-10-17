param(
  [string]$Name = "shot",
  [string]$Query = "?shot=title",
  [int]$W = 1920,
  [int]$H = 1080,
  [int]$WaitMs = 5000
)
# 霓虹拳魂 — 无头 Chrome 截图工具（需要本地服务器 127.0.0.1:8123）
# 用法：pwsh -File tools/shot.ps1 -Name battle -Query "?shot=battle&freeze=1.3"
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chrome)) { $chrome = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" }
$out = Join-Path $root ("shots\" + $Name + ".png")
$profile = Join-Path $env:TEMP ("nfshot_" + [guid]::NewGuid().ToString("N"))
$url = "http://127.0.0.1:8123/index.html" + $Query
$argList = @(
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--mute-audio",
  "--no-first-run",
  "--disable-extensions",
  "--user-data-dir=$profile",
  "--window-size=$W,$H",
  "--virtual-time-budget=$WaitMs",
  "--screenshot=$out",
  $url
)
try {
  & $chrome @argList 2>$null | Out-Null
} catch {
  Write-Host "chrome invocation returned: $($_.Exception.Message)"
}
Start-Sleep -Milliseconds 400
Remove-Item -Recurse -Force $profile -ErrorAction SilentlyContinue
if (Test-Path $out) {
  $len = (Get-Item $out).Length
  Write-Output ("OK " + $out + " (" + $len + " bytes)")
} else {
  Write-Output "FAILED: no screenshot at $out"
  exit 1
}
