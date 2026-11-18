[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('bridge','controller')][string]$Role,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][ValidatePattern('^COM[1-9][0-9]*$')][string]$Port
)
$ErrorActionPreference = 'Stop'
$firmwareRoot = Split-Path -Parent $PSScriptRoot
$targetProject = if ($Role -eq 'bridge') { Join-Path $firmwareRoot 'bridge' } else { Join-Path $firmwareRoot 'rig_controller' }
$targetEnvironment = if ($Role -eq 'bridge') { 'bridge_esp32dev' } else { 'controller_esp32dev' }
$pioCommand = Get-Command pio -ErrorAction SilentlyContinue
if ($pioCommand) { $pioExecutable = $pioCommand.Source }
else {
    $pioExecutable = Join-Path $env:USERPROFILE '.platformio/penv/Scripts/pio.exe'
    if (-not (Test-Path -LiteralPath $pioExecutable -PathType Leaf)) { throw 'PlatformIO not found. Install the VS Code PlatformIO extension or add pio to PATH.' }
}
Write-Host "UPLOAD TARGET: role=$Role environment=$targetEnvironment port=$Port project=$targetProject"
Write-Host 'This replaces firmware only on the explicitly selected serial device. Confirm the physical board identity before running.'
& $pioExecutable run -d $targetProject -e $targetEnvironment -t upload --upload-port $Port
exit $LASTEXITCODE
