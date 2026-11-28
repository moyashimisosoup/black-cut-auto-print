# Fetch the official pinned binary distribution; no execution or key creation.
# Destination must be a new directory, outside the repository.
param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$url = 'https://github.com/vslavik/winsparkle/releases/download/v0.9.4/WinSparkle-0.9.4.zip'
$expected = '6037df37fc263bd1650a1c4949681a9d40ffe991d01f35892a406cb5d103c976'
$root = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$dest = [IO.Path]::GetFullPath($Destination)
if ($dest -eq $root -or $dest.StartsWith(($root.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Choose a new destination outside the repository'
}
if (Test-Path -LiteralPath $dest) { throw 'Destination already exists; choose a new directory' }
$temp = Join-Path ([IO.Path]::GetTempPath()) ('APP033-WinSparkle-' + [guid]::NewGuid() + '.zip')
try {
  Invoke-WebRequest -Uri $url -OutFile $temp
  $actual = (Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) { throw 'Official archive SHA256 mismatch' }
  New-Item -ItemType Directory -Path $dest | Out-Null
  Expand-Archive -LiteralPath $temp -DestinationPath $dest
  Write-Output ('Verified official WinSparkle archive SHA256: ' + $actual)
  # The actual archive layout is discovered, not assumed.
  Get-ChildItem -LiteralPath $dest -Recurse -File |
    Where-Object { $_.Name -in @('WinSparkle.dll', 'winsparkle-tool.exe') -or $_.Name -match '^LICENSE(\..*)?$' } |
    ForEach-Object {
      [PSCustomObject]@{ File = $_.FullName; SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    }
} finally {
  if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
}
