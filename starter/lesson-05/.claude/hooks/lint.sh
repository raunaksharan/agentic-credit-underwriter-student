#!/usr/bin/env bash
# PostToolUse hook: lint the Python file Claude just edited and hand problems back.
# Exit 2 sends stderr to Claude, which then fixes the file; exit 0 says nothing.
input=$(cat)
file=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
if ! out=$(uv run --quiet ruff check "$file" 2>&1); then
  echo "ruff found problems in $file (fix them before moving on):" >&2
  echo "$out" >&2
  exit 2
fi
exit 0
