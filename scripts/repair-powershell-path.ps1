param(
    [switch]$Machine,
    [switch]$NoBackup
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackupDir = Join-Path $RepoRoot "tasks"

$UserKey = "HKCU\Environment"
$MachineKey = "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

function Test-RegValue {
    param(
        [string]$Key,
        [string]$Name
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & reg.exe query $Key /v $Name >$null 2>$null
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return $code -eq 0
}

function Export-RegKey {
    param(
        [string]$Key,
        [string]$Name
    )
    if ($NoBackup) {
        return
    }
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $target = Join-Path $BackupDir "$Name-$stamp.reg"
    & reg.exe export $Key $target /y | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to back up $Key to $target"
    }
    Write-Host "Backed up $Key to $target"
}

function Remove-UppercasePath {
    param(
        [string]$Key,
        [string]$Scope
    )
    if (-not (Test-RegValue -Key $Key -Name "PATH")) {
        Write-Host "$Scope uppercase PATH is already absent."
        return
    }

    Export-RegKey -Key $Key -Name "env-$Scope-before-path-fix"
    & reg.exe delete $Key /v PATH /f | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove uppercase PATH from $Scope environment. Run as administrator for machine scope."
    }
    Write-Host "Removed duplicate uppercase PATH from $Scope environment."
}

function Read-RegPath {
    param(
        [string]$Key
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & reg.exe query $Key /v Path 2>$null
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        return ""
    }
    foreach ($line in $output) {
        if ($line -match "^\s+Path\s+REG_\w+\s+(.+)$") {
            return $Matches[1]
        }
    }
    return ""
}

function Normalize-CurrentProcessPath {
    $machinePath = Read-RegPath -Key $MachineKey
    $userPath = Read-RegPath -Key $UserKey
    $combined = @($machinePath, $userPath) | Where-Object { $_ } | ForEach-Object { $_.Trim(";") }
    $pathValue = [Environment]::ExpandEnvironmentVariables(($combined -join ";"))

    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")

    Write-Host "Normalized this PowerShell process to a single Path entry."
}

Remove-UppercasePath -Key $UserKey -Scope "user"

if ($Machine) {
    Remove-UppercasePath -Key $MachineKey -Scope "machine"
} elseif (Test-RegValue -Key $MachineKey -Name "PATH") {
    Write-Warning "Machine uppercase PATH still exists. Re-run from an Administrator PowerShell with: scripts\repair-powershell-path.ps1 -Machine"
}

Normalize-CurrentProcessPath

Write-Host "Done. Restart Codex/PowerShell so new shells inherit the repaired environment."
