#requires -version 5
<#
.SYNOPSIS
  One-shot setup for the Shemesh ops-form tool on Windows.

.DESCRIPTION
  Installs Python 3.11, Git, and Ollama (via winget), clones the repo,
  installs Python dependencies, pulls the local vision model, and starts
  the web app on http://127.0.0.1:8000.

.NOTES
  Recommended invocation (paste in an elevated PowerShell window):
      powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; iex (New-Object Net.WebClient).DownloadString('https://tifult906-netizen.github.io/shemesh-ops-form/scripts/setup-windows.ps1')"

  (Don't use `iex (iwr ...).Content` - GitHub Pages serves .ps1 as
  application/octet-stream so iwr returns byte[] and iex chokes on it.
  Net.WebClient.DownloadString always returns a UTF-8 string.)

  Re-runnable: each step is skipped if already installed.
#>

# Force TLS 1.2 (older PS5 may default to 1.0/1.1 which GitHub rejects)
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

# Don't bail on the first non-fatal error - we handle errors per step.
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"   # winget output is noisy

$RepoUrl   = "https://github.com/tifult906-netizen/shemesh-ops-form"
$RepoName  = "shemesh-ops-form"
$ModelTag  = "qwen2.5vl:7b"

function Write-Step { param([string]$msg) Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Skip { param([string]$msg) Write-Host "    [--] $msg" -ForegroundColor DarkGray }
function Write-Warn { param([string]$msg) Write-Host "    [!!] $msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$msg) Write-Host "    [XX] $msg" -ForegroundColor Red }

function Test-Cmd { param([string]$name)
  $old = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
  $found = Get-Command $name -ErrorAction SilentlyContinue
  $ErrorActionPreference = $old
  return [bool]$found
}

function Refresh-Path {
  # Pick up newly-installed binaries without restarting the shell
  $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
  $user    = [System.Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = "$machine;$user"
}

function Install-Winget { param([string]$id, [string[]]$cmdNames, [string]$pretty)
  foreach ($n in $cmdNames) { if (Test-Cmd $n) { Write-Skip "$pretty already installed ($n found)"; return } }
  Write-Step "Installing $pretty via winget ($id)"
  $exit = (Start-Process -FilePath "winget" -ArgumentList @(
      "install", "--id", $id,
      "--silent",
      "--accept-source-agreements",
      "--accept-package-agreements",
      "--disable-interactivity"
    ) -NoNewWindow -Wait -PassThru).ExitCode
  if ($exit -eq 0)        { Write-Ok "$pretty installed" }
  elseif ($exit -eq -1978335189) { Write-Skip "$pretty already installed (winget reported no applicable update)" }
  else                    { Write-Warn "winget exited $exit for $pretty; continuing - re-check at the end" }
  Refresh-Path
}

# --- preflight ---------------------------------------------------------------
Write-Step "Preflight"
if (-not (Test-Cmd winget)) {
  Write-Err "winget not found. Install 'App Installer' from Microsoft Store (Win 10 1809+ / Win 11), then retry."
  Write-Host "       https://www.microsoft.com/p/app-installer/9nblggh4nns1" -ForegroundColor DarkGray
  exit 1
}
Write-Ok "winget present"

# --- tools -------------------------------------------------------------------
Install-Winget -id "Python.Python.3.11" -cmdNames @("python", "py") -pretty "Python 3.11"
Install-Winget -id "Git.Git"             -cmdNames @("git")          -pretty "Git"
Install-Winget -id "Ollama.Ollama"       -cmdNames @("ollama")       -pretty "Ollama"

# Resolve a Python executable that actually works in this session.
function Get-Python {
  if (Test-Cmd "python") { return "python" }
  if (Test-Cmd "py")     { return "py -3" }
  # Common winget install path:
  $cand = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
  if (Test-Path $cand)   { return $cand }
  return $null
}

$PY = Get-Python
if (-not $PY) {
  Write-Err "Python isn't visible in this PowerShell session yet. Close this window, open a NEW PowerShell, and re-run the installer - it'll skip the already-done steps."
  exit 1
}
Write-Ok "Using Python: $PY"

if (-not (Test-Cmd git)) {
  Write-Err "git isn't visible in this session. Same fix: close this window and re-run from a NEW PowerShell."
  exit 1
}

# --- repo --------------------------------------------------------------------
$repoDir = Join-Path $HOME $RepoName
if (Test-Path $repoDir) {
  Write-Step "Updating existing repo at $repoDir"
  Push-Location $repoDir
  & git pull --rebase
  Pop-Location
} else {
  Write-Step "Cloning repo to $repoDir"
  & git clone $RepoUrl $repoDir
  if ($LASTEXITCODE -ne 0) { Write-Err "git clone failed (exit $LASTEXITCODE)"; exit 1 }
}

# --- python deps -------------------------------------------------------------
Push-Location $repoDir
Write-Step "Creating virtualenv + installing Python deps"
if (-not (Test-Path ".venv")) {
  & $PY.Split() -m venv .venv
  if ($LASTEXITCODE -ne 0) { Write-Err "venv creation failed"; exit 1 }
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
& ".\.venv\Scripts\python.exe" -m pip install -e . --quiet
Write-Ok "Python deps installed"

# --- vision model ------------------------------------------------------------
Write-Step "Pulling local vision model ($ModelTag) - first time downloads ~5 GB"
if (-not (Test-Cmd ollama)) { Refresh-Path }
if (-not (Test-Cmd ollama)) {
  Write-Err "ollama isn't on PATH. Close this PowerShell, open a new one, and re-run the installer."
  exit 1
}
& ollama pull $ModelTag
Write-Ok "Model ready"

# --- launch ------------------------------------------------------------------
Write-Step "Starting the web app on http://127.0.0.1:8000"
Write-Host "    (Ctrl+C in this window to stop)" -ForegroundColor DarkGray
$env:SHEMESH_VISION = "ollama"
$env:SHEMESH_VISION_MODEL = $ModelTag
Start-Process "http://127.0.0.1:8000"
& ".\.venv\Scripts\python.exe" -m shemesh_ops.web
Pop-Location
