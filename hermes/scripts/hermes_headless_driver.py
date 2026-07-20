"""
Hermes Blender headless driver.

Launched by Blender (blender -b --python this_file). It:
  1. Registers the Hermes Blender addon from the skill scripts dir.
  2. Starts the addon's TCP socket server on BLENDER_HOST:BLENDER_PORT.
  3. Idles (keeping Blender's event loop alive so the socket timer runs)
     until a stop flag file appears or IDLE_TIMEOUT elapses, then quits.

The agent drives Blender from a separate process via hermes_blender.py.
"""
import os
import sys
import time

SKILL_SCRIPTS = os.path.expanduser("~/.hermes/skills/blender-mcp/scripts")
PORT = int(os.environ.get("BLENDER_PORT", "9876"))
HOST = os.environ.get("BLENDER_HOST", "localhost")
IDLE_TIMEOUT = float(os.environ.get("HERMES_IDLE_TIMEOUT", "600"))
STOP_FLAG = os.path.expanduser("~/blender-mcp/.hermes_stop")

LOG = os.path.expanduser("~/blender-mcp/hermes_driver.log")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    if SKILL_SCRIPTS not in sys.path:
        sys.path.insert(0, SKILL_SCRIPTS)

    import bpy  # Blender's bundled Python

    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)

    addon_path = os.path.join(SKILL_SCRIPTS, "hermes_blender_addon.py")
    if not os.path.exists(addon_path):
        log(f"ERROR: addon not found at {addon_path}")
        return

    # Load + register the addon module directly
    import importlib.util
    spec = importlib.util.spec_from_file_location("hermes_blender_addon", addon_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_blender_addon"] = mod
    try:
        spec.loader.exec_module(mod)
        mod.register()
        log("addon registered")
    except Exception as e:
        log(f"addon register failed: {e}")
        import traceback
        log(traceback.format_exc())
        return

    # Ensure the desired port, then start the server operator
    try:
        bpy.context.scene.blendermcp_port = PORT
    except Exception as e:
        log(f"could not set port (using default): {e}")

    # Dismiss Blender 5.x Quick Setup / splash overlay so screenshots aren't
    # blocked by the startup dialog, and force a clean solid-shaded viewport.
    try:
        prefs = bpy.context.preferences
        prefs.view.show_splash = False
        # Close any open splash region if present
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == "VIEW_3D":
                    for r in a.regions:
                        if r.type == "SPLASH":
                            try:
                                bpy.ops.wm.splash("INVOKE_DEFAULT")
                            except Exception:
                                pass
        # Force solid shading + frame all so renders are meaningful
        for a in bpy.context.screen.areas:
            if a.type == "VIEW_3D":
                a.spaces[0].shading.type = "SOLID"
                override = {"area": a, "region": a.regions[-1], "space": a.spaces[0]}
                try:
                    bpy.ops.view3d.view_all(override, center=False)
                except Exception:
                    pass
        log("splash dismissed, viewport set to solid")
    except Exception as e:
        log(f"viewport prep note: {e}")

    try:
        bpy.ops.blendermcp.start_server()
        running = getattr(bpy.context.scene, "blendermcp_server_running", False)
        log(f"server operator executed; running={running} on {HOST}:{PORT}")
    except Exception as e:
        log(f"start_server failed: {e}")
        import traceback
        log(traceback.format_exc())
        return

    log(f"READY — agent can connect to {HOST}:{PORT}")
    log(f"idle until {STOP_FLAG} appears or timeout; event loop stays free for timers")

    # Keep Blender alive WITHOUT blocking the main thread: register a low-frequency
    # timer that checks the stop flag. Returning from main() lets Blender's event
    # loop pump bpy.app.timers — which the command handlers rely on to execute.
    def idle_check():
        # stop if flag file present or idle budget exceeded
        if os.path.exists(STOP_FLAG) or (time.time() - start >= IDLE_TIMEOUT):
            log("stop condition met — shutting down")
            try:
                bpy.ops.blendermcp.stop_server()
            except Exception as e:
                log(f"stop_server note: {e}")
            try:
                bpy.ops.wm.quit_blender()
            except Exception:
                pass
            return None  # unregister timer
        return 1.0  # check again in 1s

    start = time.time()
    bpy.app.timers.register(idle_check, first_interval=1.0)
    log("driver yielded to Blender event loop")


if __name__ == "__main__":
    main()
