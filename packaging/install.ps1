[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Package = $PSScriptRoot,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'OmniFindLocalApp'),
    [switch]$SkipShortcut
)
$ErrorActionPreference = 'Stop'
$packagePath = [IO.Path]::GetFullPath($Package).TrimEnd('\')
$manifestPath = Join-Path $packagePath 'release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Release manifest missing.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.format -ne 'unsigned-one-folder-pilot') { throw 'Unsupported package manifest.' }
$versionId = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
$installPath = [IO.Path]::GetFullPath((Join-Path $InstallRoot $versionId))
$prefix = $packagePath + '\'
foreach ($entry in $manifest.files.PSObject.Properties) {
    $source = [IO.Path]::GetFullPath((Join-Path $packagePath $entry.Name))
    if (-not $source.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe package path.' }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Package file missing.' }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $entry.Value.sha256) { throw 'Package checksum mismatch.' }
}
if (Test-Path -LiteralPath $installPath) { throw 'This version already exists. No existing installation was changed.' }
if ($PSCmdlet.ShouldProcess($installPath, 'Install verified pilot files for this user')) {
    New-Item -ItemType Directory -Path $installPath | Out-Null
    foreach ($entry in $manifest.files.PSObject.Properties) {
        $target = [IO.Path]::GetFullPath((Join-Path $installPath $entry.Name))
        if (-not $target.StartsWith($installPath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe install path.' }
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $packagePath $entry.Name) -Destination $target
    }
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $installPath 'release-manifest.json')
    if (-not $SkipShortcut) {
        $shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'OmniFind Local Pilot.lnk'
        if (Test-Path -LiteralPath $shortcutPath) { throw 'Existing shortcut preserved. Installed files are ready; choose your version manually.' }
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $installPath 'OmniFind.exe'
        $shortcut.WorkingDirectory = $installPath
        $shortcut.Save()
    }
    Write-Output $installPath
}
