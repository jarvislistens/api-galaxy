#!/usr/bin/env bash
# One-shot setup. Equivalent to `make setup`, for people who would rather run a script.
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
die() { printf '\n\033[31mError:\033[0m %s\n' "$1" >&2; exit 1; }

command -v python3 >/dev/null || die "Python 3.11+ is required."
command -v node    >/dev/null || die "Node 20+ is required (https://nodejs.org)."

PY_VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
say "Python $PY_VERSION, Node $(node --version)"

say "Creating the virtualenv"
if command -v uv >/dev/null; then
  uv venv --python 3.12 .venv 2>/dev/null || uv venv .venv
  VIRTUAL_ENV=.venv uv pip install -e "apps/api[dev,keyring]"
  # Optional export dependencies. These need system libraries, so a failure here is
  # expected on a bare machine and is not fatal — the formats report themselves
  # unavailable with the reason instead.
  VIRTUAL_ENV=.venv uv pip install -e "apps/api[png,pdf]" 2>/dev/null \
    || echo "    PDF/PNG export dependencies unavailable — see the README troubleshooting section."
else
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install -e "apps/api[dev,keyring]"
  .venv/bin/python -m pip install -e "apps/api[png,pdf]" 2>/dev/null \
    || echo "    PDF/PNG export dependencies unavailable — see the README troubleshooting section."
fi

say "Installing web dependencies"
(cd apps/web && npm install --no-audit --no-fund)

[ -f .env ] || { cp .env.example .env; say "Created .env from the example"; }

say "Checking which exports are available"
.venv/bin/python -c "
from api_galaxy.exports import EXPORT_FORMATS
for f in EXPORT_FORMATS:
    print(f\"    {'ok ' if f.available else 'NO '} {f.id:11} {f.unavailable_reason}\")
" 2>/dev/null || echo "    (could not probe — is the install complete?)"

if command -v ollama >/dev/null; then
  say "Ollama found. Models installed:"
  ollama list 2>/dev/null | tail -n +2 | sed 's/^/    /' || echo "    none — run: ollama pull qwen3:4b"
else
  say "Ollama not installed (optional). Everything works without it."
fi

printf '\n\033[32mReady.\033[0m Run \033[1mmake demo\033[0m and open http://127.0.0.1:3000\n\n'
