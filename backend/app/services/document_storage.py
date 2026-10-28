import io
import re
import uuid
from pathlib import Path

from PIL import Image
from fastapi import HTTPException

from app.core.config import Settings
from app.services.document_parser import decode_text, ParseError

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def private_path(settings: Settings, key: str) -> Path:
    # Only internally generated storage keys are accepted, even for persisted rows.
    if not re.fullmatch(r"[0-9a-f]{32}\.[a-z]+", key):
        raise ValueError("Invalid storage key")
    root = Path(settings.upload_dir).resolve()
    path = root / key
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("Invalid storage path")
    return path


def validate_upload(filename: str, data: bytes) -> tuple[str, str, str]:
    name = filename.replace("\\", "/").split("/")[-1]
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "Invalid filename")
    suffix = Path(name).suffix.lower()
    mime = MIME_TYPES.get(suffix)
    if not mime:
        raise HTTPException(415, "Supported formats: PDF, TXT, MD, PNG, JPG, JPEG, WebP")
    if not data:
        raise HTTPException(422, "The file is empty")
    try:
        if suffix == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise ValueError()
        elif mime.startswith("image/"):
            with Image.open(io.BytesIO(data)) as image:
                if Image.MIME.get(image.format) != mime or image.width * image.height > 16_000_000:
                    raise ValueError()
                image.verify()
        else:
            decode_text(data)
    except (
        ValueError,
        OSError,
        ParseError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(
            422, "File content does not match its format, is damaged, or exceeds image limits"
        ) from None
    return name, mime, f"{uuid.uuid4().hex}{suffix}"
