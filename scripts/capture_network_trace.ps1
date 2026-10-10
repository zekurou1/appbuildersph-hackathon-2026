[CmdletBinding()]
param(
    [string]$Package = (Join-Path $PSScriptRoot '..\dist\OmniFindLocal'),
    [string]$PythonExecutable = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe')
)
$ErrorActionPreference = 'Stop'
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'An authorized elevated tracing session is required. No policy settings were changed.'
}
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$packagePath = [IO.Path]::GetFullPath($Package)
$output = Join-Path $project 'reports\runtime\private-network-trace'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$instance = 'OmniFind-' + [Guid]::NewGuid().ToString('N')
$trace = Join-Path $output ($instance + '.etl')
$started = $false
Push-Location -LiteralPath $project
try {
    & wpr.exe -start GeneralProfile -start Network -filemode -instancename $instance
    if ($LASTEXITCODE -ne 0) { throw 'Windows tracing could not start. Existing tracing and security settings were left unchanged.' }
    $started = $true
    & $PythonExecutable scripts/verify_package.py --package $packagePath
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic package verification failed; retain the private trace for diagnosis.' }
}
finally {
    if ($started) {
        & wpr.exe -stop $trace 'OmniFind synthetic package runtime' -skipPdbGen -instancename $instance
        if ($LASTEXITCODE -ne 0) { Write-Warning "Trace stopping failed. Stop only WPR instance $instance; do not cancel other sessions." }
    }
    Pop-Location
}
# ETL can contain unrelated private endpoints. Keep it local; never add it to Git.
# Capturing a trace alone does not pass the audit: inspect process/service attribution and lost events.
