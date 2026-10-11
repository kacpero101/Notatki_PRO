#!/bin/zsh
# Installs the Finder Quick Action "Zrób notatki" into ~/Library/Services.
# Requires lecture-notes to be installed with pipx first.
set -euo pipefail

BIN="${LECTURE_NOTES_BIN:-$HOME/.local/bin/lecture-notes}"

if [[ ! -x "$BIN" ]]; then
  echo "lecture-notes not found at $BIN" >&2
  echo "Install it first:  pipx install --python /opt/homebrew/bin/python3.12 ." >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  exec "$BIN" uninstall-quick-action
fi
exec "$BIN" install-quick-action
