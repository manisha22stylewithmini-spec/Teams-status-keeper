#!/bin/bash
# Teams Status Keeper: installs and starts the local helper (macOS).
set -e
SITE="https://teams-status-keeper.vercel.app"
DIR="$HOME/.stay-active"
mkdir -p "$DIR"
curl -fsSL "$SITE/server.py"  -o "$DIR/server.py"
curl -fsSL "$SITE/index.html" -o "$DIR/index.html"
if pgrep -f "$DIR/server.py" >/dev/null; then pkill -f "$DIR/server.py"; sleep 1; fi
echo "Starting helper. Keep this window open (Ctrl+C to quit). UI: http://localhost:8765"
exec python3 "$DIR/server.py"
