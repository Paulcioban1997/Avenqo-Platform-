Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

railway status
$health = Invoke-RestMethod -Uri "https://api.avenqo.ca/health"
$ready = Invoke-RestMethod -Uri "https://api.avenqo.ca/ready"

Write-Output "served_git_sha=$($health.git_sha)"
Write-Output "health=$($health.status)"
Write-Output "ready=$($ready.status)"