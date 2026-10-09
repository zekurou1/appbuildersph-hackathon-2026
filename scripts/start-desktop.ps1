param(
    [string]$Database,
    [string]$Model
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Run uv sync --locked from the project folder first. See README.md.'
}
$launchArguments = @('-m', 'omnifind.gui')
if ($Database) { $launchArguments += @('--db', $Database) }
if ($Model) { $launchArguments += @('--model', $Model) }
Push-Location -LiteralPath $projectRoot
try {
    & $projectPython @launchArguments
}
finally {
    Pop-Location
}
