"""Optional, byte-bound interaction geometry from one native audit execution."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

MAP_NAME = "element-map.json"
MAX_MAP_BYTES = 20 * 1024 * 1024


def native_command(script: Path, filename: str) -> list[str]:
    """Observe the same generated program once; parsed translation owns defaults."""
    png = Path(filename).with_suffix(".png")
    expected = (script.parent / png).resolve()
    if not expected.is_relative_to(script.parent.resolve()):
        # The normal audit still checks its reported output containment.
        return [sys.executable, str(script)]
    return [
        sys.executable,
        "-m",
        "graphunslopify.preview_render",
        "--geometry",
        MAP_NAME,
        "--png",
        str(expected),
        str(script),
    ]


def checked_geometry(raw: bytes, png: dict, content: bytes) -> dict:
    """Validate the original PNG container/dimensions, without redrawing it."""
    from PIL import Image

    if not 0 < len(raw) <= MAX_MAP_BYTES:
        raise ValueError("Saved element geometry exceeds the supported size")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("available") is not True
        or value.get("coordinates") != "pixels_top_left"
    ):
        raise ValueError("This run has no supported final-PNG element geometry")
    image = value.get("image")
    if (
        not isinstance(image, dict)
        or image.get("sha256") != png["sha256"]
        or hashlib.sha256(content).hexdigest() != png["sha256"]
        or image.get("name") != Path(png["path"]).name
        or not all(
            type(image.get(key)) is int and 0 < image[key] <= 32768 for key in ("width", "height")
        )
    ):
        raise ValueError("Saved element geometry does not describe this recorded PNG")
    with Image.open(io.BytesIO(content)) as actual:
        if actual.format != "PNG" or actual.size != (image["width"], image["height"]):
            raise ValueError("Saved element geometry has different image dimensions")
    elements = value.get("elements")
    if (
        not isinstance(elements, dict)
        or elements.get("schema_version") != 1
        or not isinstance(elements.get("targets"), list)
        or len(elements["targets"]) > 513
    ):
        raise ValueError("Saved element targets are unavailable or exceed capacity")
    return value


def record_geometry(folder: Path, output: Path, report: dict) -> dict:
    """Missing interaction evidence never changes the scientific audit verdict."""
    try:
        png = next(item for item in report["outputs"] if item["format"] == "png")
        path = folder / MAP_NAME
        if path.stat().st_size > MAX_MAP_BYTES:
            raise ValueError("Element geometry exceeds the supported size")
        raw = path.read_bytes()
        image_path = (folder / png["path"]).resolve()
        if not image_path.is_relative_to(folder.resolve()):
            raise ValueError("Recorded PNG escapes the figure audit directory")
        checked_geometry(raw, png, image_path.read_bytes())
        return {
            "available": True,
            "path": path.relative_to(output).as_posix(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "spec_hash": report["spec_hash"],
            "image_sha256": png["sha256"],
        }
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as problem:
        return {"available": False, "reason": str(problem) or "No PNG export was recorded"}
