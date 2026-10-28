#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '请先运行 uv sync --locked，建立项目 Python 环境。' >&2
  exit 1
fi
exec .venv/bin/python scripts/start_dev.py "$@"
