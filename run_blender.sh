#!/bin/bash
# run_blender.sh — launch Blender headless with the Hermes driver,
# wait until the socket is listening, then return (Blender keeps running
# in the background until stop_blender.sh is called or HERMES_IDLE_TIMEOUT
# elapses).
#
# Usage:
#   ./run_blender.sh                 # default port 9876, 10 min idle
#   PORT=9877 ./run_blender.sh       # custom port
#   IDLE=1800 ./run_blender.sh       # 30 min idle before auto-quit
#
# Blender must run in GUI mode (not -b) on macOS so its event loop stays
# alive; the driver dismisses the splash and forces solid shading.

set -u

PORT="${PORT:-9876}"
IDLE="${IDLE:-600}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HOME/.hermes/skills/blender-mcp/scripts/hermes_headless_driver.py"
STOP_FLAG="$HOME/blender-mcp/.hermes_stop"
LOG="$HOME/blender-mcp/hermes_driver.log"

# already running?
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Blender already listening on :$PORT — nothing to do."
    exit 0
fi

rm -f "$STOP_FLAG"

# launch detached so this script can return immediately
nohup env BLENDER_PORT="$PORT" HERMES_IDLE_TIMEOUT="$IDLE" \
    blender -noaudio --python "$DRIVER" >"$LOG" 2>&1 &
BLENDER_PID=$!

echo "Launching Blender (pid $BLENDER_PID) on :$PORT ..."

# wait for the port to come up (max ~30s)
for i in $(seq 1 30); do
    if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "READY — Hermes Blender listening on localhost:$PORT"
        exit 0
    fi
    # bail if the process died
    if ! kill -0 "$BLENDER_PID" 2>/dev/null; then
        echo "ERROR: Blender exited early. Last log:" >&2
        tail -15 "$LOG" >&2
        exit 1
    fi
    sleep 1
done

echo "WARNING: port :$PORT not listening after 30s. Check $LOG" >&2
exit 1
