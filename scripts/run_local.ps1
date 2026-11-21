# Windows helper: runs the pipeline inside WSL (Ubuntu).
#   .\scripts\run_local.ps1                 -> batch B20260630
#   .\scripts\run_local.ps1 B20260630 --fail-once silver
param([string]$BatchId = "B20260630", [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)
$proj = (Resolve-Path "$PSScriptRoot\..").Path
$wslPath = (wsl wslpath -a ($proj -replace '\', '/')).Trim()
wsl bash -lc "cd '$wslPath' && ./scripts/run_local.sh $BatchId $($Rest -join ' ')"
