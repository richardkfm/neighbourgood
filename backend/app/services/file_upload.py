"""File upload validation and storage utilities."""

import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

_IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}

UPLOAD_DIR = Path("uploads")


def validate_image_magic(data: bytes) -> bool:
    """Return True if data starts with a recognised image signature."""
    for sig in _IMAGE_SIGNATURES:
        if data[: len(sig)] == sig:
            return True
    return False


async def save_image(file: UploadFile, sub_dir: str = "") -> str:
    """
    Validate and save an uploaded image file.

    Returns the relative path where the file was saved.
    Raises HTTPException 400 on validation failure.
    """
    # Strip double extensions (e.g. file.php.jpg → use only last extension)
    original_name = file.filename or ""
    stem = Path(original_name).stem
    ext = Path(original_name).suffix.lstrip(".").lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{ext}' not allowed. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    data = await file.read()
    if not validate_image_magic(data):
        raise HTTPException(
            status_code=400,
            detail="File contents do not match a supported image format",
        )

    save_dir = UPLOAD_DIR / sub_dir if sub_dir else UPLOAD_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = save_dir / filename
    file_path.write_bytes(data)

    rel = f"/{sub_dir}/{filename}" if sub_dir else f"/{filename}"
    return rel
