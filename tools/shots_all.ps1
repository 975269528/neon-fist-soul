param(
  [string]$Prefix = "final"
)
# 批量验收截图：标题 / 战斗 / Boss / 连击 / 胜利 / 失败 / 触屏标题
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$shots = @(
  @{ name = "title";    query = "?shot=title&freeze=0.3" },
  @{ name = "battle";   query = "?shot=battle&freeze=0.2" },
  @{ name = "boss";     query = "?shot=boss&freeze=0.2" },
  @{ name = "combo";    query = "?shot=combo&freeze=0.2" },
  @{ name = "victory";  query = "?shot=victory&freeze=0.2" },
  @{ name = "gameover"; query = "?shot=gameover&freeze=0.2" },
  @{ name = "touch";    query = "?shot=battle&freeze=0.2&touch=1" }
)
foreach ($s in $shots) {
  $name = "$Prefix`_$($s.name)"
  Write-Host "=== $name ==="
  & "$root\tools\shot.ps1" -Name $name -Query $s.query -WaitMs 4500
}
