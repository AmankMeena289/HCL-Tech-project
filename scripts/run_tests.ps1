# Windows helper: runs the test suite inside WSL (Ubuntu).
$proj = (Resolve-Path "$PSScriptRoot\..").Path
$wslPath = (wsl wslpath -a ($proj -replace '\', '/')).Trim()
wsl bash -lc "cd '$wslPath' && ./scripts/run_tests.sh"
