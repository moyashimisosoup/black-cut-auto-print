# APP-033: replace a known older onefile EXE safely, with rollback.
# No downloads, no elevation, no scan/output folder or settings changes.
param(
    [string]$ExistingExe = "",
    [switch]$CheckPackageOnly
)
$ErrorActionPreference = 'Stop'
$Source = Join-Path $PSScriptRoot 'BlackCutPrintTrayCandidate.exe'
$Manifest = Join-Path $PSScriptRoot 'new_exe_sha256.txt'
$AllowedNames = @('BlackCutPrintTrayCandidate.exe', 'BlackCutPrintCandidate.exe')
$OldHashes = @(
    '466a3396b9b92ca25d28c6fad90b9ad0f8d52601cbed906ca20c6f173e8351f3', # M5 initial
    '160348312759e418f8117022e9e295d1a0f748ff51fe0de622578a47338a91b7'  # M4 initial
)
$Stage = $null
$Backup = $null
$MovedOriginal = $false
$Installed = $false
try {
    if (!(Test-Path -LiteralPath $Source -PathType Leaf)) { throw 'New executable is missing. Extract the whole ZIP first.' }
    if (!(Test-Path -LiteralPath $Manifest -PathType Leaf)) { throw 'SHA256 manifest missing. Extract the whole ZIP first.' }
    $Expected = (Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8).Trim().ToLowerInvariant()
    if ($Expected -notmatch '^[a-f0-9]{64}$') { throw 'Invalid SHA256 manifest.' }
    $NewHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($NewHash -ne $Expected) { throw 'The update executable hash does not match its manifest. No files changed.' }
    if ($CheckPackageOnly) {
        Write-Host 'PACKAGE SHA256 PASS; no EXE was modified.'
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace($ExistingExe)) {
        Write-Host 'Enter the FULL PATH to your EXISTING executable (not the newly extracted EXE):'
        $ExistingExe = Read-Host 'Existing EXE'
    }
    $ExistingExe = $ExistingExe.Trim().Trim('"')
    if ([string]::IsNullOrWhiteSpace($ExistingExe)) { throw 'No existing executable selected.' }
    $Target = [System.IO.Path]::GetFullPath($ExistingExe)
    if ($Target -ieq [System.IO.Path]::GetFullPath($Source)) {
        throw 'The new EXE and existing EXE are the same file. Extract ZIP in a different folder.'
    }
    if ($AllowedNames -notcontains [System.IO.Path]::GetFileName($Target)) {
        throw 'Unsupported EXE name. Only BlackCutPrintTrayCandidate.exe or BlackCutPrintCandidate.exe is accepted.'
    }
    if (!(Test-Path -LiteralPath $Target -PathType Leaf)) { throw 'Existing EXE not found.' }
    $OldHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($OldHash -eq $Expected) {
        Write-Host 'Already updated. No changes required.'
        exit 0
    }
    if ($OldHashes -notcontains $OldHash) {
        throw 'Existing EXE SHA256 does not match an approved APP-033 M4/M5 build. No files changed.'
    }
    $Backup = "$Target.backup-before-APP033-path-fix.exe"
    $Stage = "$Target.APP033-incoming.tmp"
    if ((Test-Path -LiteralPath $Backup) -or (Test-Path -LiteralPath $Stage)) {
        throw 'Backup or staging path already exists. Move the previous backup elsewhere before retrying.'
    }
    Write-Host "Verified existing build. Replacing: $Target"
    Write-Host "Backup: $Backup"
    Write-Host 'Ensure the app and tray icon are fully closed.'
    $Confirmation = Read-Host 'Type UPDATE to continue'
    if ($Confirmation -cne 'UPDATE') { throw 'Cancelled by user.' }

    Copy-Item -LiteralPath $Source -Destination $Stage -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) {
        throw 'Staging EXE hash mismatch. Existing EXE not changed.'
    }
    # Move refuses locked/running EXEs on Windows; do not kill processes.
    Move-Item -LiteralPath $Target -Destination $Backup -ErrorAction Stop
    $MovedOriginal = $true
    Move-Item -LiteralPath $Stage -Destination $Target -ErrorAction Stop
    $Stage = $null
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) {
        throw 'Installed EXE hash mismatch.'
    }
    $Installed = $true
    Write-Host 'SUCCESS: APP-033 updated. Old EXE preserved as a .backup-before-APP033-path-fix.exe file.'
    Write-Host 'The app is not started automatically. Scan/print permissions remain OFF at startup.'
    exit 0
}
catch {
    Write-Host "UPDATE ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($MovedOriginal -and !$Installed) {
        try {
            if (Test-Path -LiteralPath $Target) {
                Remove-Item -LiteralPath $Target -Force -ErrorAction Stop
            }
            Move-Item -LiteralPath $Backup -Destination $Target -ErrorAction Stop
            Write-Host 'Rollback succeeded. Original EXE restored.'
        } catch {
            Write-Host 'Rollback could not complete. The original EXE remains at the backup path. Restore it manually.' -ForegroundColor Red
        }
    }
    exit 1
}
finally {
    if ($Stage -and (Test-Path -LiteralPath $Stage)) {
        Remove-Item -LiteralPath $Stage -Force -ErrorAction SilentlyContinue
    }
}
