#!/bin/bash
# stop_blender.sh — cleanly stop the headless Hermes Blender instance.
# Sets the driver's stop-flag; the idle timer then quits Blender.
#
# Usage: ./stop_blender.sh [port]

set -u
PORT="${PORT:-9876}"
STOP_FLAG="$HOME/blender-mcp/.hermes_stop"

if ! lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Nothing listening on :$PORT — already stopped."
    exit 0
fi

touch "$STOP_FLAG"
echo "Stop flag set; waiting for Blender to quit ..."

for i in $(seq 1 20); do
    if ! lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "Blender stopped cleanly."
        rm -f "$STOP_FLAG"
        exit 0
    fi
    sleep 1
done

echo "WARNING: Blender did not exit within 20s; forcing." >&2
pkill -f "hermes_headless_driver.py" 2>/dev/null
exit 1
