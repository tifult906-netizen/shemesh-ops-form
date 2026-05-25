#requires -version 5
<#
.SYNOPSIS
  One-shot setup for the Shemesh ops-form tool on Windows.

.DESCRIPTION
  Installs Python 3.11, Git, and Ollama (via winget), clones the repo,
  installs Python dependencies, pulls the local vision model, and starts
  the web app on http://127.0.0.1:8000.

.NOTES
  Run by double-clicking, or from PowerShell:
      iwr https://tifult906-netizen.github.io/shemesh-ops-form/scripts/setup-windows.ps1 | iex

  Re-runnable: each step is skipped if already installed.
#>

$ErrorActionPreference = "Stop"
$RepoUrl   = "https://github.com/tifult906-netizen/shemesh-ops-form"
$RepoName  = "shemesh-ops-form"
$ModelTag  = "qwen2.5vl:7b"

function Write-Step { param([string]$msg) Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$msg) Write-Host "    ✓ $msg" -ForegroundColor Green }
function Write-Skip { param([string]$msg) Write-Host "    • $msg" -ForegroundColor DarkGray }

function Test-Cmd { param([string]$name) try { Get-Command $name -ErrorAction Stop | Out-Null; $true } catch { $false } }

function Install-Winget { param([string]$id, [string]$name)
  if (Test-Cmd $name) { Write-Skip "$name already installed"; return }
  Write-Step "Installing $name via winget ($id)"
  winget install --id $id --silent --accept-source-agreements --accept-package-agreements
  Write-Ok "$name installed"
}

# --- preflight ---------------------------------------------------------------
if (-not (Test-Cmd winget)) {
  Write-Host "winget is required (Windows 10 1809+ / Windows 11). Get it from the Microsoft Store: 'App Installer'." -ForegroundColor Red
  exit 1
}

# --- tools -------------------------------------------------------------------
Install-Winget -id "Python.Python.3.11" -name "python"
Install-Winget -id "Git.Git"             -name "git"
Install-Winget -id "Ollama.Ollama"       -name "ollama"

# refresh PATH so the new installs are visible in this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# --- repo --------------------------------------------------------------------
$repoDir = Join-Path $HOME $RepoName
if (Test-Path $repoDir) {
  Write-Step "Updating existing repo at $repoDir"
  Push-Location $repoDir
  git pull --rebase
  Pop-Location
} else {
  Write-Step "Cloning repo to $repoDir"
  git clone $RepoUrl $repoDir
}

# --- python deps -------------------------------------------------------------
Push-Location $repoDir
Write-Step "Creating virtualenv + installing Python deps"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install -e . --quiet
Write-Ok "Python deps installed"

# --- vision model ------------------------------------------------------------
Write-Step "Pulling local vision model ($ModelTag) — first time downloads ~5 GB"
ollama pull $ModelTag
Write-Ok "Model ready"

# --- launch ------------------------------------------------------------------
Write-Step "Starting the web app on http://127.0.0.1:8000"
Write-Host "    (Ctrl+C in this window to stop)" -ForegroundColor DarkGray
$env:SHEMESH_VISION = "ollama"
$env:SHEMESH_VISION_MODEL = $ModelTag
Start-Process "http://127.0.0.1:8000"
python -m shemesh_ops.web
Pop-Location
