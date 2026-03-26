#!/bin/bash
# Install ccrelay slash command for Claude Code
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/commands/relay.md"
TARGET="$HOME/.claude/commands/relay.md"

if [ ! -f "$SOURCE" ]; then
    echo "Error: $SOURCE not found" >&2
    exit 1
fi

mkdir -p "$(dirname "$TARGET")"
cp "$SOURCE" "$TARGET"
echo "Installed /relay command to $TARGET"
