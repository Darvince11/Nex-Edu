"""Uploaded images are untrusted: decode, check, and re-encode them before storing.

Re-encoding to a fresh PNG drops everything except pixels (EXIF, GPS, embedded
scripts or polyglot payloads). SVG is refused outright because it can carry script.
"""

from __future__ import annotations

import io

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_SOURCE_PIXELS = 4096 * 4096  # refuse "decompression bombs" before decoding them
LOGO_MAX_SIDE = 512


def clean_logo(data: bytes) -> bytes:
    """A school logo as PNG bytes, at most LOGO_MAX_SIDE px on its longest side."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError("The logo must be 1 MB or smaller.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ValidationError("Upload a PNG, JPG or WebP image.")
            width, height = probe.size
            if width * height > MAX_SOURCE_PIXELS:
                raise ValidationError("That image is too large. Use one under 4096 by 4096 pixels.")
            probe.verify()  # structural check; the image must be reopened afterwards
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image = image.convert("RGBA")
            image.thumbnail((LOGO_MAX_SIDE, LOGO_MAX_SIDE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValidationError("That file isn't a valid image.") from exc
    return out.getvalue()
