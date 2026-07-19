# blender-mcp — Hermes Agent fork

A fork of [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) (MIT)
adapted to be driven by **Hermes Agent** instead of Claude.

The upstream project connects Blender to an LLM through the **Model Context
Protocol (MCP)**. Hermes is not an MCP client, so this fork removes the MCP
layer entirely and talks to the Blender addon **directly over a local TCP
socket** — no `mcp` package, no `httpx`, no external services, no telemetry.

```
Hermes Agent  ── hermes_blender.py (socket client) ──▶  Blender addon  (listens on localhost:9876)
```

## What changed vs upstream

| Area | Upstream | This fork |
|---|---|---|
| Transport | MCP server (`mcp`) + socket | **Direct socket client** — no MCP, no `mcp`/`httpx` deps |
| AI client | Claude (MCP host) | Hermes Agent (calls a plain Python module) |
| Telemetry | Anonymous usage + **screenshot upload** to Supabase | **Removed entirely** + addon consent defaults to `off` |
| Addon branding | "Blender MCP" / "Connect to Claude" | "Hermes Blender" / "Connect to Hermes Agent" |
| Command set | unchanged | **identical** — every upstream command works 1:1 |

The Blender addon's socket protocol is byte-for-byte compatible, so the new
client also drives the original upstream addon.

## Repository layout

```
blender-mcp/                      # this fork repo (origin = nanoatom81/blender-mcp)
  README.md                       # this file
  addon.py                        # upstream addon (reference)
  src/blender_mcp/                # upstream MCP server (kept for reference; not used by Hermes)
  hermes/                         # <-- the Hermes skill (copy this into your Hermes setup)
    SKILL.md
    scripts/hermes_blender.py           # socket client the agent calls (pure stdlib)
    scripts/hermes_blender_addon.py     # rebranded addon to install into Blender
    references/command-reference.md
```

## Install into Hermes

```bash
# from this repo root
mkdir -p ~/.hermes/skills/blender-mcp
cp -R hermes/SKILL.md hermes/scripts hermes/references ~/.hermes/skills/blender-mcp/
```

Then, in Blender: **Edit ▸ Preferences ▸ Add-ons ▸ Install**, select
`hermes/scripts/hermes_blender_addon.py`, enable **Interface: Hermes Blender**,
open the **Hermes Blender** tab in the 3D View sidebar (`N`), and click
**Connect to Hermes Agent**.

## Quick test (Blender running + addon connected)

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/blender-mcp/scripts"))
from hermes_blender import Blender
b = Blender()
print(b.get_scene_info())
b.execute_code("import bpy; bpy.ops.mesh.primitive_cube_add()")
print(b.get_viewport_screenshot())
```

## Re-sync from upstream

```bash
git fetch upstream
git merge upstream/main   # then re-apply the branding/telemetry patches
```
