# Build only; does not publish, sign, or modify an existing installation.
param(
  [Parameter(Mandatory=$true)][string]$PublicKey,
  [Parameter(Mandatory=$true)][string]$WinSparkleDll,
  [Parameter(Mandatory=$true)][string]$DllSha256,
  [Parameter(Mandatory=$true)][string]$WinSparkleLicense,
  [Parameter(Mandatory=$true)][string]$Iscc,
  [string]$StagingFeedUrl = ""
)
$ErrorActionPreference = 'Stop'
if ([Convert]::FromBase64String($PublicKey).Length -ne 32) { throw 'Invalid EdDSA public key' }
if ($PublicKey -notmatch '^[A-Za-z0-9+/]{43}=$') { throw 'Invalid public key encoding' }
$dll = (Resolve-Path -LiteralPath $WinSparkleDll).Path
$license = (Resolve-Path -LiteralPath $WinSparkleLicense).Path
$compiler = (Resolve-Path -LiteralPath $Iscc).Path
if ((Split-Path $dll -Leaf) -ne 'WinSparkle.dll') { throw 'Expected official x64 WinSparkle.dll' }
if ($DllSha256 -notmatch '^[a-fA-F0-9]{64}$' -or
    (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $DllSha256) {
  throw 'WinSparkle DLL SHA256 mismatch'
}
# A filename and hash alone do not establish that the binary is x64.
$bytes = [System.IO.File]::ReadAllBytes($dll)
if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x4d -or $bytes[1] -ne 0x5a) {
  throw 'Invalid DLL header'
}
$pe = [BitConverter]::ToInt32($bytes, 0x3c)
if ($pe -lt 64 -or $pe -gt ($bytes.Length - 6) -or
    [BitConverter]::ToUInt32($bytes, $pe) -ne 0x4550 -or
    [BitConverter]::ToUInt16($bytes, ($pe + 4)) -ne 0x8664) {
  throw 'Expected AMD64 PE DLL'
}
if ($StagingFeedUrl) {
  $uri = $null
  if ($StagingFeedUrl -notmatch '^https://[A-Za-z0-9.-]+(?::[0-9]+)?/[A-Za-z0-9._/-]+\.xml$' -or
      -not [Uri]::TryCreate($StagingFeedUrl, [UriKind]::Absolute, [ref]$uri) -or
      $uri.Host -in @('github.com','www.github.com','api.github.com','githubusercontent.com') -or
      $uri.Host.EndsWith('.githubusercontent.com')) {
    throw 'Staging requires a separate HTTPS XML endpoint without credentials or query'
  }
}
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'dist\managed'
if ($StagingFeedUrl) { $out = Join-Path $root 'dist\managed-staging' }
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('APP033-build-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $stage,$out -Force | Out-Null
try {
  Copy-Item (Join-Path $root 'app') (Join-Path $stage 'app') -Recurse
  $identity = Join-Path $stage 'app\update_identity.py'
  $source = Get-Content -LiteralPath $identity -Raw
  if (!$source.Contains('PUBLIC_KEY = ""')) { throw 'Unexpected trust anchor' }
  $source = $source.Replace('PUBLIC_KEY = ""', ('PUBLIC_KEY = "' + $PublicKey + '"'))
  if ($StagingFeedUrl) {
    $production = 'FEED_URL = "https://github.com/moyashimisosoup/black-cut-auto-print/releases/download/update-feed/appcast.xml"'
    if (!$source.Contains($production)) { throw 'Unexpected production feed' }
    $source = $source.Replace($production, ('FEED_URL = "' + $StagingFeedUrl + '"'))
  }
  $source | Set-Content -LiteralPath $identity -Encoding utf8
  $version = python -c "import sys; sys.path.insert(0,sys.argv[1]); from version_info import APP_VERSION; print(APP_VERSION)" (Join-Path $stage 'app')
  if ($LASTEXITCODE -ne 0 -or $version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$') { throw 'Bad version' }
  python -m PyInstaller --noconfirm --clean --onefile --windowed --name BlackCutPrint --paths (Join-Path $stage 'app') --hidden-import pystray._win32 --add-binary "$dll;." --distpath $out --workpath (Join-Path $stage 'work') --specpath $stage (Join-Path $stage 'app\m4_operator_ui.py')
  if ($LASTEXITCODE -ne 0) { throw 'Managed EXE build failed' }
  & $compiler "/DBuildVersion=$version" "/DBuildExe=$out\BlackCutPrint.exe" "/DLicenseFile=$license" "/O$out" (Join-Path $PSScriptRoot 'managed.iss')
  if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
  Get-FileHash -LiteralPath (Join-Path $out "BlackCutPrint-Setup-$version.exe") -Algorithm SHA256
} finally {
  Remove-Item -LiteralPath $stage -Recurse -Force
}
