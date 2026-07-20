"""
blender_ctl.py — programmatic lifecycle control for the Hermes Blender addon.

This lets the Hermes agent start/stop/inspect the headless Blender instance
without the user touching a terminal. The agent is the single point of contact.

Usage (from the agent):
    from blender_ctl import ensure_blender, stop_blender, blender_running

    ensure_blender()                       # start if not already up (blocks ~10s)
    b = Blender()                          # connect (from hermes_blender)
    ... do work ...
    # optionally leave it running, or:
    stop_blender()                         # clean shutdown
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

SKILL_SCRIPTS = os.path.expanduser("~/.hermes/skills/blender-mcp/scripts")
DRIVER = os.path.join(SKILL_SCRIPTS, "hermes_headless_driver.py")
STOP_FLAG = os.path.expanduser("~/blender-mcp/.hermes_stop")
LOG = os.path.expanduser("~/blender-mcp/hermes_driver.log")
DEFAULT_PORT = int(os.environ.get("BLENDER_PORT", "9876"))
IDLE_TIMEOUT = float(os.environ.get("HERMES_IDLE_TIMEOUT", "600"))


def blender_running(port: int = DEFAULT_PORT) -> bool:
    """True if something is listening on localhost:<port>."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("localhost", port)) == 0


def _blender_binary() -> str:
    # Prefer the brew-linked binary; fall back to the app bundle.
    for cand in ("/opt/homebrew/bin/blender", "/usr/local/bin/blender",
                 "/Applications/Blender.app/Contents/MacOS/Blender"):
        if os.path.exists(cand):
            return cand
    # last resort: hope it's on PATH
    return "blender"


def ensure_blender(port: int = DEFAULT_PORT, idle_timeout: float = IDLE_TIMEOUT,
                   timeout: float = 40.0) -> bool:
    """
    Start Blender headless (if not already listening) and wait until ready.
    Returns True if Blender is listening on <port> by the end.
    """
    if blender_running(port):
        return True
    if not os.path.exists(DRIVER):
        raise FileNotFoundError(f"Hermes driver not found: {DRIVER}")
    if not os.path.exists(_blender_binary()):
        raise RuntimeError("Blender binary not found — install via 'brew install --cask blender'")

    os.makedirs(os.path.dirname(STOP_FLAG), exist_ok=True)
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)

    env = dict(os.environ)
    env["BLENDER_PORT"] = str(port)
    env["HERMES_IDLE_TIMEOUT"] = str(idle_timeout)

    # Launch detached (no pty) so this process can return.
    subprocess.Popen(
        [_blender_binary(), "-noaudio", "--python", DRIVER],
        env=env, stdout=open(LOG, "a"), stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if blender_running(port):
            return True
        time.sleep(1.0)
    raise TimeoutError(f"Blender did not start listening on :{port} within {timeout}s. See {LOG}")


def stop_blender(port: int = DEFAULT_PORT, timeout: float = 25.0) -> bool:
    """
    Cleanly stop the headless Blender instance by setting the driver's stop-flag.
    The idle timer then quits Blender. Returns True if stopped.
    """
    if not blender_running(port):
        return True
    # Setting the flag makes the driver's idle_check() quit on its next tick.
    with open(STOP_FLAG, "w") as f:
        f.write("stop")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not blender_running(port):
            try:
                os.remove(STOP_FLAG)
            except OSError:
                pass
            return True
        time.sleep(1.0)
    # force if needed
    subprocess.run(["pkill", "-f", "hermes_headless_driver.py"], check=False)
    return not blender_running(port)


if __name__ == "__main__":
    # CLI for quick manual use / debugging
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "start":
        print("starting..." if ensure_blender() else "FAILED to start")
    elif action == "stop":
        print("stopped" if stop_blender() else "FAILED to stop")
    elif action == "status":
        print("RUNNING" if blender_running() else "STOPPED")
