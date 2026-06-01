#!/usr/bin/env bash
# 开发模式启动 JarDiff（不打包，直接用 venv 运行）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "未找到虚拟环境，正在创建并安装依赖…"
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip -q
  "$VENV/bin/python" -m pip install -r "$ROOT/requirements-app.txt"
fi

exec "$VENV/bin/python" -m jardiff_app.app "$@"
