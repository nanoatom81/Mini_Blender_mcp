# Hermes Blender — command reference

This is the exact command set the addon understands. Every command is sent over
the socket as `{"type": <command>, "params": {<kwargs>}}` and returns
`{"status": "success", "result": <data>}` or `{"status": "error", "message": <text>}`.

The Python client `hermes_blender.py` wraps each of these as a method on
`Blender`. Method → command mapping:

| Client method | Command `type` | Key params |
|---|---|---|
| `get_scene_info()` | `get_scene_info` | — |
| `get_object_info(name)` | `get_object_info` | `name` |
| `execute_code(code)` | `execute_code` | `code` |
| `get_viewport_screenshot(max_size, filepath, format)` | `get_viewport_screenshot` | `max_size`, `filepath`, `format` |
| `get_polyhaven_status()` | `get_polyhaven_status` | — |
| `get_polyhaven_categories(asset_type)` | `get_polyhaven_categories` | `asset_type` ∈ hdris/textures/models/all |
| `search_polyhaven_assets(asset_type, categories)` | `search_polyhaven_assets` | `asset_type`, `categories` |
| `download_polyhaven_asset(asset_id, asset_type, resolution, file_format)` | `download_polyhaven_asset` | `asset_id`, `asset_type`, `resolution`, `file_format` |
| `set_texture(object_name, texture_id)` | `set_texture` | `object_name`, `texture_id` |
| `get_sketchfab_status()` | `get_sketchfab_status` | — |
| `search_sketchfab_models(query, categories, count, downloadable)` | `search_sketchfab_models` | `query`, `categories`, `count`, `downloadable` |
| `get_sketchfab_model_preview(uid)` | `get_sketchfab_model_preview` | `uid` |
| `download_sketchfab_model(uid, target_size)` | `download_sketchfab_model` | `uid`, `normalize_size`(True), `target_size` |
| `get_hyper3d_status()` | `get_hyper3d_status` | — |
| `create_rodin_job(text_prompt, images, bbox_condition)` | `create_rodin_job` | `text_prompt`, `images`, `bbox_condition` |
| `poll_rodin_job_status(subscription_key, request_id)` | `poll_rodin_job_status` | `subscription_key` OR `request_id` |
| `import_generated_asset(name, task_uuid, request_id)` | `import_generated_asset` | `name`, `task_uuid` OR `request_id` |
| `get_hunyuan3d_status()` | `get_hunyuan3d_status` | — |
| `create_hunyuan_job(text_prompt, image)` | `create_hunyuan_job` | `text_prompt`, `image` |
| `poll_hunyuan_job_status(job_id)` | `poll_hunyuan_job_status` | `job_id` |
| `import_generated_asset_hunyuan(name, zip_file_url)` | `import_generated_asset_hunyuan` | `name`, `zip_file_url` |
| `get_telemetry_consent()` | `get_telemetry_consent` | — (addon-internal; defaults to off) |

## Notes
- All asset-library commands (Poly Haven / Sketchfab / Hyper3D / Hunyuan3D) are
  **only registered by the addon when their checkbox is enabled** in the Blender
  panel. Calling them while disabled returns an "Unknown command type" error —
  check `get_*_status()` first.
- `execute_code` runs in Blender's main thread with `bpy` in scope. It is the
  escape hatch for anything not covered above (procedural modelling, animation,
  shader nodes, scene export, etc.).
- `get_viewport_screenshot` requires a 3D viewport to be visible in Blender.
