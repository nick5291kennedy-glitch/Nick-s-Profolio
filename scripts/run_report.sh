#!/bin/zsh
set -euo pipefail

ROOT="/Users/nicholaskennedy/Documents/New project"
LOG_DIR="$ROOT/logs"

mkdir -p "$LOG_DIR"
cd "$ROOT"

/usr/bin/python3 "$ROOT/scripts/generate_briefing.py" | tee -a "$LOG_DIR/latest-run.log"
