# Create one git worktree from origin/main for a lane branch and path.
# Refuses when the path exists or the branch exists. Does not overwrite.
# Does not merge, push, enrol, SSH, or change devices or printers.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\new-agent-worktree.ps1 -Branch feature/agent-lane-console -Path C:\Users\henok\src\AI-PLAYBOOK-lane-console
#
# The new branch does not track origin/main. Push is a separate step,
# and only for the lane branch: git push -u origin <branch>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Branch,
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Git = "C:\Users\henok\AppData\Local\GitHubDesktop\app-3.5.4\resources\app\git\mingw64\bin\git.exe"
$SrcRoot = "C:\Users\henok\src"
$MainWorkspace = "C:\Users\henok\src\AI-PLAYBOOK.md"

function Refuse([string]$Message) {
    [Console]::Error.WriteLine("ERROR: $Message")
    exit 2
}

function Get-Upstream([string]$Worktree) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $name = & $Git -C $Worktree rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" 2>$null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) {
        return ""
    }
    return (($name | Out-String).Trim())
}

function Same-Or-Under([string]$Child, [string]$Parent) {
    $childPath = [System.IO.Path]::GetFullPath($Child).TrimEnd('\')
    $parentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\')
    if ($childPath.Equals($parentPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $childPath.StartsWith($parentPath + '\', [System.StringComparison]::OrdinalIgnoreCase)
}

if (-not (Test-Path -LiteralPath $Git)) {
    Refuse "The GitHub Desktop git executable is missing. Do not use another git."
}

$Branch = $Branch.Trim()
if ($Branch -eq "") {
    Refuse "Pass a branch name."
}
if ($Branch -match '^(main|master|HEAD)$' -or $Branch -match '(^|/)(main|master)$' -or $Branch.StartsWith("origin/")) {
    Refuse "Refusing branch '$Branch'. Do not create or update main."
}

$checked = & $Git check-ref-format --branch $Branch
if ($LASTEXITCODE -ne 0 -or $checked -ne $Branch) {
    Refuse "Branch name '$Branch' is not a single valid git branch. Stop."
}

try {
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
} catch {
    Refuse "Path '$Path' is not a usable path."
}

if (-not (Same-Or-Under $full $SrcRoot) -or $full.Equals([System.IO.Path]::GetFullPath($SrcRoot).TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)) {
    Refuse "Path must be a new folder under C:\Users\henok\src."
}
if (Same-Or-Under $full $MainWorkspace) {
    Refuse "Refusing '$full'. Do not checkout the main workspace while another agent is in it."
}
if (Test-Path -LiteralPath $full) {
    Refuse "Path already exists: $full. Stop. Do not overwrite."
}
$parent = Split-Path -Parent $full
if (-not (Test-Path -LiteralPath $parent)) {
    Refuse "Parent folder does not exist: $parent. Stop. Do not create it."
}

$root = Split-Path -Parent $PSScriptRoot
& $Git -C $root rev-parse --is-inside-work-tree 1>$null
if ($LASTEXITCODE -ne 0) {
    Refuse "Run this script from a checkout of this repo."
}

& $Git -C $root show-ref --verify --quiet "refs/heads/$Branch"
if ($LASTEXITCODE -eq 0) {
    Refuse "Branch '$Branch' already exists locally. Stop. Do not overwrite."
}

Write-Output "Fetching origin (no merge, no push)."
& $Git -C $root fetch origin
if ($LASTEXITCODE -ne 0) {
    Refuse "Fetch failed. No worktree was created."
}

$base = (& $Git -C $root rev-parse --verify "refs/remotes/origin/main").Trim()
if ($LASTEXITCODE -ne 0 -or $base -eq "") {
    Refuse "origin/main is not available. No worktree was created."
}

& $Git -C $root show-ref --verify --quiet "refs/remotes/origin/$Branch"
if ($LASTEXITCODE -eq 0) {
    Refuse "Branch 'origin/$Branch' already exists. Stop. Do not overwrite."
}
& $Git -C $root show-ref --verify --quiet "refs/heads/$Branch"
if ($LASTEXITCODE -eq 0) {
    Refuse "Branch '$Branch' already exists locally. Stop. Do not overwrite."
}
if (Test-Path -LiteralPath $full) {
    Refuse "Path already exists: $full. Stop. Do not overwrite."
}

$listed = & $Git -C $root worktree list --porcelain
foreach ($line in @($listed)) {
    if ($line -like "worktree *") {
        $existing = $line.Substring(9).Trim()
        if ($existing.Equals($full, [System.StringComparison]::OrdinalIgnoreCase)) {
            Refuse "A worktree already uses $full. Stop. Do not overwrite."
        }
    }
}

Write-Output "Adding worktree $full on $Branch at $base."
& $Git -C $root worktree add -b $Branch $full origin/main
if ($LASTEXITCODE -ne 0) {
    Refuse "worktree add failed. Stop. Do not overwrite."
}

$created = (& $Git -C $full rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $created -ne $base) {
    Refuse "New worktree HEAD did not match origin/main. Leave it in place and do not overwrite."
}

$upstream = Get-Upstream $full
if ($upstream -ne "") {
    if ($upstream -ne "origin/main") {
        Refuse "Branch $Branch tracks '$upstream'. Stop. Do not push."
    }
    & $Git -C $full branch --unset-upstream
    if ($LASTEXITCODE -ne 0) {
        Refuse "Could not clear upstream on $Branch. Do not push. The branch must not track origin/main."
    }
}

$upstream = Get-Upstream $full
if ($upstream -ne "") {
    Refuse "Branch $Branch still tracks '$upstream'. Do not push."
}

Write-Output "Created $Branch at $full."
Write-Output "HEAD $created from origin/main. No upstream. No merge. No push. No enrolment."
exit 0
