#!/usr/bin/env python3
"""
hermes_blender.py — Hermes Agent client for driving Blender.

This is a fork of ahujasid/blender-mcp (MIT) adapted for Hermes Agent.
The original project wraps Blender's socket addon behind the Model Context
Protocol (MCP) so Claude can call it. Hermes is not an MCP client, so this
module drops the MCP layer entirely and talks to the running Blender addon
directly over a TCP socket (default localhost:9876).

The Blender side is `addon.py` (installed into Blender). It opens a socket
server and executes JSON commands of the shape:
    {"type": "<command>", "params": {<kwargs>}}
and replies with:
    {"status": "success", "result": <data>}
    {"status": "error",    "message": "<text>"}

This module mirrors the original server's command set 1:1, but exposes it as
plain Python functions the agent can call. No external services, no telemetry,
no `mcp` dependency.

Quick start
-----------
    from hermes_blender import Blender
    b = Blender()                       # connects to localhost:9876
    print(b.get_scene_info())
    b.execute_code("import bpy; bpy.ops.mesh.primitive_cube_add()")

Requirements: a Blender instance with the Hermes Blender addon enabled and
"Connect" pressed (or auto-connect enabled). The addon listens on the port
configured in Blender's addon preferences (default 9876).
"""

from __future__ import annotations

import base64
import json
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["Blender", "BlenderError", "BlenderConnectionError"]

DEFAULT_HOST = os.getenv("BLENDER_HOST", "localhost")
DEFAULT_PORT = int(os.getenv("BLENDER_PORT", "9876"))
SOCKET_TIMEOUT = float(os.getenv("BLENDER_TIMEOUT", "180.0"))


class BlenderError(Exception):
    """Raised when Blender returns an error status or the command fails."""


class BlenderConnectionError(BlenderError):
    """Raised when we cannot reach the Blender addon socket."""


def _require_blender_module(name: str, install_hint: str) -> None:
    """Helper for callers that want to push .blend / glb files from disk."""
    import importlib

    try:
        importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise BlenderError(
            f"Missing optional dependency '{name}'. {install_hint}"
        ) from exc


class BlenderConnection:
    """A persistent TCP connection to the Blender addon socket server."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> bool:
        if self.sock is not None:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            return True
        except OSError as exc:
            self.sock = None
            raise BlenderConnectionError(
                f"Could not connect to Blender at {self.host}:{self.port}. "
                "Make sure the Hermes Blender addon is enabled and connected "
                "in Blender (Sidebar > Hermes Blender > Connect)."
            ) from exc

    def disconnect(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            finally:
                self.sock = None

    def _receive_full_response(self, buffer_size: int = 8192) -> bytes:
        """Read until we have a complete JSON document or time out."""
        chunks: List[bytes] = []
        self.sock.settimeout(SOCKET_TIMEOUT)
        try:
            while True:
                try:
                    chunk = self.sock.recv(buffer_size)
                except socket.timeout:
                    break
                if not chunk:
                    if not chunks:
                        raise BlenderConnectionError(
                            "Connection closed before any data arrived"
                        )
                    break
                chunks.append(chunk)
                # Cheap check: did we already receive a full JSON object?
                try:
                    json.loads(b"".join(chunks).decode("utf-8"))
                    break
                except json.JSONDecodeError:
                    continue
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as exc:
            self.sock = None
            raise BlenderConnectionError(
                f"Socket error while receiving from Blender: {exc}"
            ) from exc

        if not chunks:
            raise BlenderConnectionError("No data received from Blender")
        return b"".join(chunks)

    def send_command(
        self, command_type: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a command and return the `result` payload (or raise)."""
        if self.sock is None and not self.connect():
            raise BlenderConnectionError("Not connected to Blender")

        command = {"type": command_type, "params": params or {}}
        try:
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            raw = self._receive_full_response()
            response = json.loads(raw.decode("utf-8"))
        except socket.timeout:
            self.sock = None
            raise BlenderError(
                "Timeout waiting for Blender. If Blender is running headless "
                "(blender -b), commands never execute — run it with a GUI or "
                "via 'xvfb-run -a blender'."
            )
        except json.JSONDecodeError as exc:
            raise BlenderError(f"Invalid JSON response from Blender: {exc}") from exc

        if response.get("status") == "error":
            raise BlenderError(response.get("message", "Unknown error from Blender"))
        return response.get("result", {})


class Blender:
    """
    High-level Blender controller for Hermes Agent.

    Wraps every command the Hermes Blender addon understands. Methods return
    parsed Python objects (dicts/lists) so the agent can reason over them.

    Screenshot/image methods return local file paths or base64 strings so the
    agent can attach them to its reply (MEDIA: path) or describe them.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._conn = BlenderConnection(host=host, port=port)

    # -- connection management --------------------------------------------
    def connect(self) -> bool:
        return self._conn.connect()

    def disconnect(self) -> None:
        self._conn.disconnect()

    def is_connected(self) -> bool:
        try:
            self._conn.send_command("get_polyhaven_status")
            return True
        except BlenderError:
            return False

    # -- core scene commands ----------------------------------------------
    def get_scene_info(self) -> Dict[str, Any]:
        """Names, counts and a condensed object list for the live scene."""
        return self._conn.send_command("get_scene_info")

    def get_object_info(self, name: str) -> Dict[str, Any]:
        """Detailed transform / mesh / material info for one object."""
        return self._conn.send_command("get_object_info", {"name": name})

    def execute_code(self, code: str) -> str:
        """
        Run arbitrary Blender Python in Blender's main thread.
        Returns the captured stdout. Powerful — use for anything the
        dedicated helpers don't cover (modelling, animation, nodes, etc.).
        """
        result = self._conn.send_command("execute_code", {"code": code})
        return result.get("result", "") if isinstance(result, dict) else str(result)

    # -- screenshots -------------------------------------------------------
    def get_viewport_screenshot(
        self, max_size: int = 1000, return_base64: bool = False
    ) -> str:
        """
        Capture the 3D viewport.

        Returns the path to a temp PNG (default) or base64 PNG data when
        `return_base64=True` (handy when you want to embed it directly).
        The agent can attach the returned path via MEDIA: for visual review.
        """
        temp_path = os.path.join(
            tempfile.gettempdir(), f"hermes_blender_shot_{os.getpid()}.png"
        )
        result = self._conn.send_command(
            "get_viewport_screenshot",
            {"max_size": max_size, "filepath": temp_path, "format": "png"},
        )
        if isinstance(result, dict) and result.get("error"):
            raise BlenderError(result["error"])
        if not os.path.exists(temp_path):
            raise BlenderError("Screenshot file was not created by Blender")
        if return_base64:
            with open(temp_path, "rb") as fh:
                data = base64.b64encode(fh.read()).decode("ascii")
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return data
        return temp_path

    # -- Poly Haven (opt-in in Blender addon) ------------------------------
    def get_polyhaven_status(self) -> Dict[str, Any]:
        return self._conn.send_command("get_polyhaven_status")

    def get_polyhaven_categories(self, asset_type: str = "hdris") -> str:
        result = self._conn.send_command(
            "get_polyhaven_categories", {"asset_type": asset_type}
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        cats = result.get("categories", {})
        ordered = sorted(cats.items(), key=lambda kv: kv[1], reverse=True)
        return "\n".join(f"- {k}: {v} assets" for k, v in ordered)

    def search_polyhaven_assets(
        self, asset_type: str = "all", categories: Optional[str] = None
    ) -> str:
        result = self._conn.send_command(
            "search_polyhaven_assets",
            {"asset_type": asset_type, "categories": categories},
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        assets = result.get("assets", {})
        ordered = sorted(
            assets.items(),
            key=lambda kv: kv[1].get("download_count", 0),
            reverse=True,
        )
        out = [f"Found {result.get('total_count')} assets; showing {len(ordered)}:"]
        for aid, data in ordered:
            out.append(f"- {data.get('name', aid)} (ID: {aid})")
        return "\n".join(out)

    def download_polyhaven_asset(
        self,
        asset_id: str,
        asset_type: str,
        resolution: str = "1k",
        file_format: Optional[str] = None,
    ) -> str:
        result = self._conn.send_command(
            "download_polyhaven_asset",
            {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "resolution": resolution,
                "file_format": file_format,
            },
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        if result.get("success"):
            msg = result.get("message", "Asset downloaded and imported")
            if asset_type == "hdris":
                msg += ". HDRI set as world environment."
            elif asset_type == "textures":
                msg += f". Material '{result.get('material','')}'."
            elif asset_type == "models":
                msg += ". Imported into scene."
            return msg
        return f"Failed: {result.get('message', 'unknown error')}"

    def set_texture(self, object_name: str, texture_id: str) -> str:
        result = self._conn.send_command(
            "set_texture", {"object_name": object_name, "texture_id": texture_id}
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        if result.get("success"):
            return (
                f"Applied texture '{texture_id}' to {object_name} "
                f"via material '{result.get('material','')}'."
            )
        return f"Failed: {result.get('message', 'unknown error')}"

    # -- Sketchfab (opt-in) ------------------------------------------------
    def get_sketchfab_status(self) -> Dict[str, Any]:
        return self._conn.send_command("get_sketchfab_status")

    def search_sketchfab_models(
        self, query: str, categories: Optional[str] = None,
        count: int = 20, downloadable: bool = True,
    ) -> str:
        result = self._conn.send_command(
            "search_sketchfab_models",
            {
                "query": query,
                "categories": categories,
                "count": count,
                "downloadable": downloadable,
            },
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        models = result.get("results", []) or []
        if not models:
            return f"No models found matching '{query}'"
        out = [f"Found {len(models)} models for '{query}':"]
        for m in models:
            out.append(f"- {m.get('name','?')} (UID: {m.get('uid','?')})")
            out.append(f"  License: {m.get('license',{}).get('label','?')}")
        return "\n".join(out)

    def get_sketchfab_model_preview(self, uid: str) -> str:
        """Return a path to a temp PNG thumbnail of a Sketchfab model."""
        result = self._conn.send_command("get_sketchfab_model_preview", {"uid": uid})
        if isinstance(result, dict) and result.get("error"):
            raise BlenderError(result["error"])
        data = base64.b64decode(result["image_data"])
        fmt = result.get("format", "jpeg")
        path = os.path.join(
            tempfile.gettempdir(), f"hermes_sketchfab_{uid}.{fmt}"
        )
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def download_sketchfab_model(self, uid: str, target_size: float) -> str:
        result = self._conn.send_command(
            "download_sketchfab_model",
            {"uid": uid, "normalize_size": True, "target_size": target_size},
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        if result.get("success"):
            objs = ", ".join(result.get("imported_objects", [])) or "none"
            out = f"Imported model. Objects: {objs}."
            if result.get("dimensions"):
                d = result["dimensions"]
                out += f" Dimensions: {d[0]:.2f}x{d[1]:.2f}x{d[2]:.2f}m."
            return out
        return f"Failed: {result.get('message','unknown error')}"

    # -- Hyper3D Rodin (opt-in) --------------------------------------------
    def get_hyper3d_status(self) -> Dict[str, Any]:
        return self._conn.send_command("get_hyper3d_status")

    def create_rodin_job(
        self,
        text_prompt: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        image_urls: Optional[List[str]] = None,
        bbox_condition: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Submit a text- or image-conditioned 3D generation job. Returns task ids."""
        images = None
        if image_paths:
            images = []
            for p in image_paths:
                with open(p, "rb") as fh:
                    images.append(
                        (Path(p).suffix, base64.b64encode(fh.read()).decode("ascii"))
                    )
        elif image_urls:
            images = list(image_urls)
        params: Dict[str, Any] = {"text_prompt": text_prompt, "images": images}
        if bbox_condition:
            params["bbox_condition"] = [
                int(float(i) / max(bbox_condition) * 100) for i in bbox_condition
            ]
        return self._conn.send_command("create_rodin_job", params)

    def poll_rodin_job_status(
        self, subscription_key: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Any:
        kwargs = {}
        if subscription_key:
            kwargs["subscription_key"] = subscription_key
        elif request_id:
            kwargs["request_id"] = request_id
        return self._conn.send_command("poll_rodin_job_status", kwargs)

    def import_generated_asset(
        self, name: str, task_uuid: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Any:
        kwargs = {"name": name}
        if task_uuid:
            kwargs["task_uuid"] = task_uuid
        elif request_id:
            kwargs["request_id"] = request_id
        return self._conn.send_command("import_generated_asset", kwargs)

    # -- Hunyuan3D (opt-in) ------------------------------------------------
    def get_hunyuan3d_status(self) -> Dict[str, Any]:
        return self._conn.send_command("get_hunyuan3d_status")

    def create_hunyuan_job(
        self, text_prompt: Optional[str] = None, input_image_url: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._conn.send_command(
            "create_hunyuan_job",
            {"text_prompt": text_prompt, "image": input_image_url},
        )

    def poll_hunyuan_job_status(self, job_id: str) -> Any:
        return self._conn.send_command("poll_hunyuan_job_status", {"job_id": job_id})

    def import_generated_asset_hunyuan(self, name: str, zip_file_url: str) -> Any:
        return self._conn.send_command(
            "import_generated_asset_hunyuan",
            {"name": name, "zip_file_url": zip_file_url},
        )


# -- CLI smoke test -------------------------------------------------------
def _main() -> None:
    """`python hermes_blender.py` — verify Blender is reachable."""
    try:
        b = Blender()
        info = b.get_scene_info()
        print("Connected to Blender.")
        print(json.dumps(info, indent=2))
    except BlenderError as exc:
        print(f"Blender not reachable: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    _main()
