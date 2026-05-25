#!/usr/bin/env bash
# One-shot setup for the Shemesh ops-form tool on macOS / Linux.
#
# Run with:
#   curl -fsSL https://tifult906-netizen.github.io/shemesh-ops-form/scripts/setup-mac.sh | bash
#
# Installs Python, Git, Ollama (via Homebrew on macOS / apt on Debian/Ubuntu),
# clones the repo, installs Python deps, pulls the local vision model, and
# starts the web app on http://127.0.0.1:8000.
#
# Re-runnable: each step is skipped if already installed.

set -euo pipefail

REPO_URL="https://github.com/tifult906-netizen/shemesh-ops-form"
REPO_DIR="$HOME/shemesh-ops-form"
MODEL_TAG="qwen2.5vl:7b"

step() { printf "\n\033[36m==> %s\033[0m\n" "$*"; }
ok()   { printf "    \033[32m✓\033[0m %s\n" "$*"; }
skip() { printf "    \033[90m•\033[0m %s\n" "$*"; }

has() { command -v "$1" >/dev/null 2>&1; }

install_mac() {
  if ! has brew; then
    step "Installing Homebrew"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  for pkg in python@3.11 git ollama; do
    if brew list "$pkg" >/dev/null 2>&1; then
      skip "$pkg already installed"
    else
      step "Installing $pkg"
      brew install "$pkg"
    fi
  done
}

install_linux() {
  if has apt-get; then
    step "Installing python / git via apt"
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-venv python3-pip git curl
  elif has dnf; then
    sudo dnf install -y python3 python3-pip git curl
  elif has pacman; then
    sudo pacman -Sy --noconfirm python git curl
  else
    echo "Unsupported Linux distro. Install python3, git, and curl manually then re-run."
    exit 1
  fi

  if ! has ollama; then
    step "Installing Ollama"
    curl -fsSL https://ollama.com/install.sh | sh
  else
    skip "ollama already installed"
  fi
}

# --- platform routing --------------------------------------------------------
case "$(uname -s)" in
  Darwin*) install_mac ;;
  Linux*)  install_linux ;;
  *) echo "Unsupported OS: $(uname -s)"; exit 1 ;;
esac

# --- repo --------------------------------------------------------------------
if [ -d "$REPO_DIR" ]; then
  step "Updating existing repo at $REPO_DIR"
  git -C "$REPO_DIR" pull --rebase
else
  step "Cloning repo to $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

# --- python deps -------------------------------------------------------------
step "Creating virtualenv + installing Python deps"
PY=python3
[ -d .venv ] || $PY -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install -e . --quiet
ok "Python deps installed"

# --- vision model ------------------------------------------------------------
step "Pulling local vision model ($MODEL_TAG) — first time downloads ~5 GB"
ollama pull "$MODEL_TAG"
ok "Model ready"

# --- launch ------------------------------------------------------------------
step "Starting the web app on http://127.0.0.1:8000  (Ctrl+C to stop)"
export SHEMESH_VISION=ollama
export SHEMESH_VISION_MODEL="$MODEL_TAG"
( sleep 2 && (open http://127.0.0.1:8000 2>/dev/null || xdg-open http://127.0.0.1:8000 2>/dev/null || true) ) &
python -m shemesh_ops.web
