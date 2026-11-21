# Upload every changed file to GitHub in one step.
#   .\scripts\push_changes.ps1                       # default message
#   .\scripts\push_changes.ps1 "Updated the KPI docs"
param([string]$Message = "Update project files")

Set-Location (Split-Path $PSScriptRoot -Parent)

$changes = git status --porcelain
if (-not $changes) {
    Write-Host "No changes - GitHub is already up to date."
    exit 0
}

Write-Host "Changed files:"
$changes | ForEach-Object { Write-Host "  $_" }

git add -A
git commit -q -m $Message
if ($LASTEXITCODE -ne 0) { Write-Host "Commit failed."; exit 1 }
git push
if ($LASTEXITCODE -ne 0) { Write-Host "Push failed - check your internet connection or GitHub login."; exit 1 }
Write-Host "Done: changes are on https://github.com/AmankMeena289/HCL-Tech-project"
