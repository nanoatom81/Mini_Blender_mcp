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

## Install this skill

Option A — into the Hermes skill dir (recommended):
```bash
# from this repo root
mkdir -p ~/.hermes/skills/blender-mcp
cp -R hermes/SKILL.md hermes/scripts hermes/references ~/.hermes/skills/blender-mcp/
```

Option B — point your code at this repo's `hermes/scripts` directly (no copy),
using the path this skill file lives in:
```python
import os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../hermes
sys.path.insert(0, os.path.join(here, "scripts"))
from hermes_blender import Blender
```

## Prerequisites (one-time, the user does this in Blender)

1. Install Blender 3.0+ (https://www.blender.org/download).
2. In Blender: **Edit ▸ Preferences ▸ Add-ons ▸ Install**, select
   `hermes/scripts/hermes_blender_addon.py`, then enable **Interface: Hermes Blender**.
3. In the 3D Viewport sidebar (press `N`): open the **Hermes Blender** tab and
   click **Connect to Hermes Agent**. The addon opens a socket on
   `localhost:9876` (configurable in the panel).
4. Optional integrations (Poly Haven, Sketchfab, Hyper3D Rodin, Hunyuan3D) are
   checkboxes in the same panel; they need API keys in the add-on preferences.

> The agent cannot install the addon or start Blender itself — these are GUI
> steps the user performs. If `BlenderConnectionError` is raised, tell the user
> to open Blender, enable the addon, and click Connect.

## How the agent uses this skill

```python
import sys, os
# resolve the scripts dir (adjust if installed elsewhere)
skill_scripts = os.path.expanduser("~/.hermes/skills/blender-mcp/scripts")
sys.path.insert(0, skill_scripts)
from hermes_blender import Blender, BlenderError

b = Blender()  # host/port from BLENDER_HOST / BLENDER_PORT, default localhost:9876
try:
    print(b.get_scene_info())
    b.execute_code("import bpy; bpy.ops.mesh.primitive_cube_add(location=(0,0,0))")
    shot = b.get_viewport_screenshot()   # returns a local PNG path
    print("screenshot:", shot)            # attach via MEDIA: in your reply
except BlenderError as e:
    print("Blender error:", e)
```

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
  `search_polyhaven_assets`, `download_polyhaven_asset`, `set_texture`.
- Sketchfab: `get_sketchfab_status`, `search_sketchfab_models(query, ...)`,
  `get_sketchfab_model_preview(uid)`, `download_sketchfab_model(uid, target_size)`.
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
2. Make changes via `execute_code` (preferred for precise control) or asset helpers.
3. Screenshot **after** and `get_scene_info()` to confirm.
4. Iterate. If something looks wrong, investigate before proceeding.

## Privacy note
The original project shipped anonymous telemetry that uploaded tool usage and
**screenshots to a remote Supabase instance**. That telemetry lived in the MCP
server, which this fork removes entirely. The addon's consent flag now **defaults
to off**, and nothing in this skill transmits data anywhere — all communication
stays on the local socket between the agent and your Blender.

## Files
- `hermes/scripts/hermes_blender.py` — the socket client (the agent uses this). No
  third-party deps beyond the stdlib.
- `hermes/scripts/hermes_blender_addon.py` — the Blender addon to install into Blender.
- `hermes/references/command-reference.md` — full command/parameter reference.
- Upstream: https://github.com/ahujasid/blender-mcp (MIT).
