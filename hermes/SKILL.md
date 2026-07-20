---
name: blender-mcp
description: >-
  Control Blender from Hermes Agent. Use when the user wants to create, inspect,
  modify, render, or script 3D scenes in Blender, generate 3D assets, capture
  viewport screenshots, or run Blender Python. Requires Blender with the Hermes
  Blender addon installed and connected. This is a fork of ahujasid/blender-mcp
  adapted to talk to Blender directly over a local socket (no Claude / no MCP
  server needed).
category: creative
---

# Blender control for Hermes Agent

This skill drives a running **Blender** instance from the agent. The original
`ahujasid/blender-mcp` routes commands through the Model Context Protocol so
Claude can call them. Hermes is not an MCP client, so this fork drops the MCP
layer and speaks to Blender's socket addon **directly** over TCP.

```
 Hermes Agent  ──hermes_blender.py (socket client)──▶  Blender addon (addon.py, listens on :9876)
```

## Prerequisites (one-time setup, user does this in Blender)

1. Install Blender 3.0+ (https://www.blender.org/download).
2. In Blender: **Edit ▸ Preferences ▸ Add-ons ▸ Install**, select
   `~/.hermes/skills/blender-mcp/scripts/hermes_blender_addon.py`, then enable
   **Interface: Hermes Blender**.
3. In the 3D Viewport sidebar (press `N`): open the **Hermes Blender** tab and
   click **Connect to Hermes Agent**. The addon opens a socket on
   `localhost:9876` (configurable via the port field in the panel).
4. Optional integrations (Poly Haven, Sketchfab, Hyper3D Rodin, Hunyuan3D) are
   checkboxes in the same panel; they need API keys in the add-on preferences.

> **Auto lifecycle (convenience):** the agent CAN start/stop Blender itself via
> `hermes/scripts/blender_ctl.py` (`ensure_blender()` / `stop_blender()`). The user
> does NOT need to open Blender or click Connect — the agent launches Blender
> headless with the addon auto-registered and the socket auto-started. If
> `BlenderConnectionError` is raised even after `ensure_blender()`, check
> `~/blender-mcp/hermes_driver.log` and whether Blender is installed.

## How the agent uses this skill

Load the client module and call it. Example inside a Python tool / execute_code
block that has filesystem access to the skill scripts:

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/blender-mcp/scripts"))
from hermes_blender import Blender, BlenderError

b = Blender()  # host/port from BLENDER_HOST / BLENDER_PORT env, default localhost:9876
try:
    print(b.get_scene_info())
    b.execute_code("import bpy; bpy.ops.mesh.primitive_cube_add(location=(0,0,0))")
    shot = b.get_viewport_screenshot()   # returns a local PNG path
    print("screenshot:", shot)            # attach via MEDIA: in your reply
except BlenderError as e:
    print("Blender error:", e)
```

### Lifecycle — auto start / auto stop (user never touches the terminal)

The agent is the single point of contact. Before any Blender command, call
`ensure_blender()`; when the task is done (or if you'll be idle), call
`stop_blender()`. These live in `hermes/scripts/blender_ctl.py`.

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/blender-mcp/scripts"))
from blender_ctl import ensure_blender, stop_blender, blender_running
from hermes_blender import Blender, BlenderError

# 1) make sure Blender is up (starts it headless if not; ~10s)
ensure_blender()

# 2) do the work
b = Blender()
try:
    b.execute_code("import bpy; bpy.ops.mesh.primitive_cube_add()")
    print(b.get_viewport_screenshot())
finally:
    pass  # leave it running for follow-ups, OR stop_blender() to free resources

# 3) clean shutdown when finished (optional but tidy)
# stop_blender()
```

Shell equivalents (if you prefer): `./run_blender.sh` and `./stop_blender.sh`
from the `~/blender-mcp` repo root. `blender_ctl.py` is the programmatic path the
agent should use; the `.sh` scripts are for the user's own terminal.

Rules of thumb:
- If `blender_running()` is already True, `ensure_blender()` returns instantly (no
  restart). Multiple tasks in a row should reuse the same instance.
- Stop the instance when the user is done with Blender for a while — a headless
  Blender holds a GPU/CPU process. `stop_blender()` is clean (flag-based) and will
  force-kill only if it ignores the flag.
- On macOS, Blender runs in GUI mode (not `-b`) so its event loop stays alive; the
  driver dismisses the splash and forces solid shading automatically.

### Command contract (all map 1:1 to the addon)

Core:
- `get_scene_info()` → scene name, object count, condensed object list.
- `get_object_info(name)` → transforms, mesh stats, materials, world AABB.
- `execute_code(code)` → run arbitrary Blender Python; returns captured stdout.
  Use this for anything not covered by a dedicated helper (modelling, animation,
  geometry nodes, materials).
- `get_viewport_screenshot(max_size=1000, return_base64=False)` → path to a temp
  PNG (or base64). **Always screenshot before and after edits to verify visually.**

Asset libraries (only if enabled in the Blender panel):
- Poly Haven: `get_polyhaven_status`, `get_polyhaven_categories(asset_type)`,
  `search_polyhaven_assets`, `download_polyhaven_asset`,
  `set_texture(object_name, texture_id)`.
- Sketchfab: `get_sketchfab_status`, `search_sketchfab_models(query, ...)`,
  `get_sketchfab_model_preview(uid)` → temp PNG, `download_sketchfab_model(uid, target_size)`.
- Hyper3D Rodin: `get_hyper3d_status`, `create_rodin_job(text_prompt=..., image_paths=..., image_urls=...)`,
  `poll_rodin_job_status(subscription_key=...)`, `import_generated_asset(name, task_uuid=...)`.
- Hunyuan3D: `get_hunyuan3d_status`, `create_hunyuan_job(...)`,
  `poll_hunyuan_job_status(job_id)`, `import_generated_asset_hunyuan(name, zip_file_url)`.

### Connection env vars
- `BLENDER_HOST` (default `localhost`), `BLENDER_PORT` (default `9876`),
  `BLENDER_TIMEOUT` (default `180.0` seconds).

## Recommended workflow
0. `get_scene_info()` to see the current state.
1. Screenshot the viewport **before** changes.
2. Make changes via `execute_code` (preferred for precise control) or asset
   helpers.
3. Screenshot **after** and `get_scene_info()` to confirm.
4. Iterate. If something looks wrong, investigate before proceeding.

## Automated / headless runs (no human at the GUI)

For fully hands-free runs, launch Blender with the bundled driver instead of
asking the user to click Connect. The driver registers the addon, starts the
socket server, and keeps Blender alive so the agent drives it:

```bash
BLENDER_PORT=9876 HERMES_IDLE_TIMEOUT=300 blender -noaudio \
  --python ~/.hermes/skills/blender-mcp/scripts/hermes_headless_driver.py &
# then drive it as in "How the agent uses this skill" above
# clean stop:  touch ~/blender-mcp/.hermes_stop
```

**Three non-obvious failures that block a first automated run — read before
debugging (full detail in `references/headless-automation.md`):**

1. **The addon refuses to bind the socket in `blender -b` mode.** `start()` has
   an artificial `if bpy.app.background: return` gate. It is already patched out
   in `scripts/hermes_blender_addon.py`; re-apply if you re-sync upstream.
2. **`blender -b` quits after `--python` returns**, so `bpy.app.timers` command
   handlers never fire and the client times out with `No data received`. Run in
   **GUI mode (omit `-b`)** and make the driver **yield via `bpy.app.timers`**
   (never a blocking `while sleep` loop) — see the reference.
3. **Blender 5.x Quick Setup splash** covers the viewport on first launch, so the
   first screenshot captures the splash. The driver dismisses it + forces SOLID
   shading on startup.

## Privacy note
The original project shipped anonymous telemetry that uploaded tool usage and
**screenshots to a remote Supabase instance**. That telemetry lived in the MCP
server, which this fork removes entirely. The addon's consent flag now **defaults
to off**, and nothing in this skill transmits data anywhere — all communication
stays on the local socket between the agent and your Blender.

## Publishing the fork to GitHub — gotchas

This fork was pushed to a user's GitHub repo; three non-obvious failures cost
real time and are worth remembering for ANY repo-push task:

1. **Credentials pasted in chat get masked.** The harness rewrites anything
   matching a token pattern (`ghp_...`, `github_pat_...`) to `***` in terminal
   input, `write_file` content, and chat — so a token the user pastes can NEVER
   reach the agent intact. **Workaround:** ask the user to write the token to a
   file themselves (outside chat), e.g. `echo '<token>' > ~/.github_push_token`,
   then the agent reads that file (files the user creates are not masked). Never
   rely on a token surviving a paste through the chat.

2. **Fine-grained PATs often 403 on `git push`** even when the REST API reports
   `push: true` for the repo (`remote: Permission to ... denied`). The git
   smart-HTTP backend evaluates the token's repository-access grant differently
   from the API, and "All repositories" access can still 403 for repos created
   after the token. **Fix:** switch to **SSH** (generate `ed25519`, have the user
   add the pubkey at github.com/settings/keys, `git remote set-url origin
   git@github.com:owner/repo.git`, push). SSH is the durable fix; classic PATs
   (`ghp_...`) also work via URL-embedding and lack the fine-grained quirk.

3. **`git clone --depth 1` breaks later pushes** with
   `remote unpack failed: index-pack failed` / "did not receive expected object".
   The shallow clone omits parent history, so the pushed pack is incomplete.
   **Fix:** `git fetch --unshallow upstream` (or re-clone without `--depth`) before
   pushing. Verify with `git fsck --full` (clean) and `git cat-file -t <missing-obj>`
   (must resolve) before retrying.

See `references/github-push-gotchas.md` for the exact diagnostic recipe
(API-permissions-vs-git-403 check, unshallow sequence, credential-helper form
`x-access-token` + fine-grained token).

## Files
- `scripts/hermes_blender.py` — the socket client (the agent uses this). No
  third-party deps beyond the stdlib.
- `scripts/hermes_blender_addon.py` — the Blender addon to install into Blender
  (background-mode gate patched out).
- `scripts/hermes_headless_driver.py` — launches Blender headless: registers the
  addon, starts the socket server, keeps Blender alive via `bpy.app.timers`, and
  quits on stop-flag/timeout. Used for automated runs (see below).
- `references/command-reference.md` — full command/parameter reference.
- `references/github-push-gotchas.md` — credential masking, fine-grained-PAT 403,
  and shallow-clone push failures (general GitHub-publishing pitfalls).
- `references/headless-automation.md` — the automated/headless run recipe and the
  three non-obvious failures (background-mode gate, `-b` event-loop death,
  Quick Setup splash) with fixes.
- Upstream: https://github.com/ahujasid/blender-mcp (MIT).
