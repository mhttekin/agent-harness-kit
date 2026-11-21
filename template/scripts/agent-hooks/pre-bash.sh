#!/usr/bin/env bash
# PreToolUse adapter for Claude Code and Codex: the hook JSON arrives on stdin; exit 2 with a reason on stderr blocks
# the Bash command (scripts/bash_guard.py says which commands and why).
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
python="$root/.venv/bin/python"
[[ -x "$python" ]] || python=python3
exec "$python" "$root/scripts/bash_guard.py"
