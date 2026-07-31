#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

if [[ -x ".venv/bin/fluxdl" ]]; then
  exec .venv/bin/fluxdl "$@"
fi

if command -v uv >/dev/null 2>&1; then
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$project_dir/.uv-cache}"
  exec uv run fluxdl "$@"
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --editable .

exec .venv/bin/fluxdl "$@"
