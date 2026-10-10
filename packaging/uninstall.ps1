[CmdletBinding(SupportsShouldProcess)]
param([Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{12}$')][string]$VersionId)
$ErrorActionPreference = 'Stop'
$installRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'OmniFindLocalApp')).TrimEnd('\')
$target = [IO.Path]::GetFullPath((Join-Path $installRoot $VersionId))
if (-not $target.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe uninstall target.' }
if (-not (Test-Path -LiteralPath (Join-Path $target 'release-manifest.json') -PathType Leaf)) { throw 'Pilot installation manifest missing.' }
$ancestor = $target
while ($ancestor) {
    if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked uninstall paths are excluded.' }
    $parent = [IO.Directory]::GetParent($ancestor)
    $ancestor = if ($parent) { $parent.FullName } else { $null }
}
if (Get-ChildItem -LiteralPath $target -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1) { throw 'Linked package contents are excluded.' }
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'OmniFind Local Pilot.lnk'
if ($PSCmdlet.ShouldProcess($target, 'Remove this pilot version; preserve index and original files')) {
    if (Test-Path -LiteralPath $shortcutPath) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        if ([IO.Path]::GetFullPath($shortcut.TargetPath) -eq (Join-Path $target 'OmniFind.exe')) {
            Remove-Item -LiteralPath $shortcutPath
        }
    }
    Remove-Item -LiteralPath $target -Recurse
}
# Deliberately never touch %LOCALAPPDATA%\OmniFindLocal or any selected source folder.
