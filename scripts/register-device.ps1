# Register this Windows computer once, then keep its own worker polling.
# Run it on the new computer, from a clone of this repo, with the console
# tunnel already open. It does not enrol the Office PC, does not change
# printers, and does not clear a print queue.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-device.ps1 -Name "Family Laptop"
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-device.ps1 -Name "Family Laptop" -Code "<one-time-code>" -Console "http://127.0.0.1:8080"
#
# A missing -Code asks for the console operator and mints a fresh code.
# The code is used immediately and is not written to a file. The device
# secret is written only to the token file and is not printed. If that
# file already exists, enrolment is skipped and the worker starts.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [string]$Code = "",
    [string]$Console = "http://127.0.0.1:8080",
    [string]$TokenFile = "",
    [string]$Operator = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Fold-Text([string]$Value) {
    $parts = @($Value -split "\s+" | Where-Object { $_ -ne "" })
    return (($parts -join " ").ToLowerInvariant().TrimEnd("."))
}

function Refuse([string]$Message) {
    [Console]::Error.WriteLine("ERROR: $Message")
    exit 2
}

$hostname = Fold-Text ([System.Net.Dns]::GetHostName())
if ($hostname -eq "banya-family-pl" -or $hostname.StartsWith("banya-family-pl.")) {
    Refuse "BANYA-FAMILY-PL is the development PC. Run this script on the other Windows computer. Do not enrol this one."
}

$display = ($Name -replace "\s+", " ").Trim()
$foldedName = Fold-Text $display
$blocked = @(
    "office pc",
    "banya-family-pl",
    "not-the-second-endpoint",
    "bead5785f3674aaeb92c189f8c1b5b8c"
)
if ($blocked -contains $foldedName -or $foldedName.StartsWith("banya-family-pl.")) {
    Refuse "Choose a new display name. Do not use Office PC, BANYA-FAMILY-PL, or the existing Office PC device id."
}
if ($display -notmatch "^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$") {
    Refuse "Display name must be 1 to 40 letters, numbers, spaces, dots, or dashes."
}

try {
    $consoleUri = [Uri]$Console
} catch {
    Refuse "Pass the loopback console, for example http://127.0.0.1:8080."
}
$consoleHost = $consoleUri.Host.ToLowerInvariant()
if ($consoleUri.Scheme -ne "http" -or ($consoleHost -ne "127.0.0.1" -and $consoleHost -ne "localhost")) {
    Refuse "The worker accepts HTTP only for http://127.0.0.1 or http://localhost. Open the SSH tunnel first."
}
if ($consoleUri.Port -lt 1) {
    Refuse "Pass a console origin with a port, for example http://127.0.0.1:8080."
}
if ($consoleUri.AbsolutePath -ne "/" -and $consoleUri.AbsolutePath -ne "") {
    Refuse "Pass the console origin, not a path."
}
$Console = "{0}://{1}:{2}" -f $consoleUri.Scheme, $consoleHost, $consoleUri.Port
$origin = $Console

$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $root "integrations\endpoint_worker.py"))) {
    Refuse "Stop. Run this script from a clone that contains integrations\endpoint_worker.py."
}
if (-not (Test-Path -LiteralPath (Join-Path $root "integrations\remote_worker.py"))) {
    Refuse "Stop. This clone has no integrations\remote_worker.py. Update it from main before registering."
}
Set-Location -LiteralPath $root

if (-not $TokenFile) {
    if (-not $env:LOCALAPPDATA) {
        Refuse "LOCALAPPDATA is unset. Pass -TokenFile with an absolute path outside this repo."
    }
    $TokenFile = Join-Path $env:LOCALAPPDATA "AI-PLAYBOOK\device-secret"
}
if (-not [System.IO.Path]::IsPathRooted($TokenFile)) {
    Refuse "The token file must be an absolute path outside this repo."
}

function Start-Worker {
    Write-Host "Starting this computer's worker. It polls the console for approved jobs for this device only. Ctrl+C stops polling. The enrolment stays."
    & $Python -m integrations.remote_worker serve --console $Console --token-file $TokenFile
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $TokenFile) {
    Write-Host "This computer already has a device secret. Enrolment was not repeated."
    Start-Worker
}

function Read-PlainSecret([Security.SecureString]$Secure) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

if (-not $Code) {
    if (-not $Operator) {
        $Operator = Read-Host "Console operator username"
    }
    $securePassword = Read-Host -AsSecureString "Console operator password"
    $password = Read-PlainSecret $securePassword
    $securePassword.Dispose()
    $loginBody = @{ username = $Operator; password = $password } | ConvertTo-Json -Compress
    $password = $null
    try {
        $loginResponse = Invoke-WebRequest -Method Post -Uri ($Console + "/api/auth/login") -UseBasicParsing -ContentType "application/json; charset=utf-8" -Body $loginBody -Headers @{ Origin = $origin }
    } catch {
        $loginBody = $null
        Refuse "The console did not accept the operator sign-in. No enrolment code was created."
    }
    $loginBody = $null
    $login = $loginResponse.Content | ConvertFrom-Json
    $csrf = [string]$login.csrf_token
    $login = $null
    $setCookie = $loginResponse.Headers["Set-Cookie"]
    $loginResponse = $null
    $sessionId = ""
    foreach ($cookie in @($setCookie)) {
        if ($cookie -match "console_session=([^;]+)") {
            $sessionId = $Matches[1]
            break
        }
    }
    if (-not $csrf -or -not $sessionId) {
        $csrf = $null
        $sessionId = $null
        Refuse "The console did not accept the operator sign-in. No enrolment code was created."
    }
    try {
        $mintResponse = Invoke-WebRequest -Method Post -Uri ($Console + "/api/devices/enrolment") -UseBasicParsing -ContentType "application/json; charset=utf-8" -Body "{}" -Headers @{
            Origin = $origin
            "X-CSRF-Token" = $csrf
            Cookie = ("console_session=" + $sessionId)
        }
    } catch {
        $csrf = $null
        $sessionId = $null
        Refuse "The console did not issue an enrolment code. The operator needs connectors:manage on the loopback console."
    }
    $csrf = $null
    $sessionId = $null
    $minted = $mintResponse.Content | ConvertFrom-Json
    $mintResponse = $null
    $Code = [string]$minted.enrolment_code
    $minted = $null
    Write-Host "A fresh enrolment code was issued and will be used now. It was not saved to a file."
}

if ($Code -notmatch "^[A-Za-z0-9_-]{16,80}$") {
    Refuse "The enrolment code is not usable. Mint another one and run this script again."
}

& $Python -m integrations.endpoint_worker enrol --console $Console --code=$Code --name $display --token-file $TokenFile
$Code = $null
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
Start-Worker
