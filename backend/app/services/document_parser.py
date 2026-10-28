"""Untrusted file parser. Run only in a time/memory-limited subprocess, never in ASGI."""

import io
import json
import resource
import sys
import warnings
from pathlib import Path

import pymupdf
import pytesseract
from charset_normalizer import from_bytes
from PIL import Image

Image.MAX_IMAGE_PIXELS = 16_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)


class ParseError(ValueError):
    pass


def decode_text(data: bytes) -> str:
    if not data:
        raise ParseError("The file is empty")
    try:
        text = data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig")
    except UnicodeError:
        match = from_bytes(data).best()
        if not match or match.chaos > 0.1:
            raise ParseError("Cannot detect text encoding; save the file as UTF-8") from None
        text = str(match)
    if any(ord(c) < 32 and c not in "\n\r\t\f" for c in text):
        raise ParseError("Binary data is not a text document")
    return text


def image_text(image: Image.Image, languages: str) -> str:
    image.load()
    if image.width * image.height > Image.MAX_IMAGE_PIXELS:
        raise ParseError("Image exceeds the 16 megapixel processing limit")
    return pytesseract.image_to_string(image.convert("RGB"), lang=languages, timeout=30).strip()


def parse_file(path: str, mime: str, max_pages: int, max_chars: int, languages: str) -> list[dict]:
    pages = []
    if mime in ("text/plain", "text/markdown"):
        pages = [{"page": None, "text": decode_text(Path(path).read_bytes())}]
    elif mime == "application/pdf":
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ParseError("Password-protected PDFs are not supported")
            if not 0 < doc.page_count <= max_pages:
                raise ParseError(f"PDF must contain 1–{max_pages} pages")
            for number, page in enumerate(doc, 1):
                text = page.get_text(sort=True).strip()
                # OCR text-poor pages, including mixed text/scanned PDFs.
                if len(text) < 40:
                    scale = min(2, (16_000_000 / max(1, page.rect.width * page.rect.height)) ** 0.5)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    ocr = image_text(Image.open(io.BytesIO(pix.tobytes("png"))), languages)
                    text = ocr or text
                pages.append({"page": number, "text": text})
                if sum(len(p["text"]) for p in pages) > max_chars:
                    raise ParseError(f"Extracted text exceeds {max_chars} characters")
    else:
        with Image.open(path) as image:
            pages = [{"page": None, "text": image_text(image, languages)}]
    if sum(len(p["text"]) for p in pages) > max_chars:
        raise ParseError(f"Extracted text exceeds {max_chars} characters")
    if not any(p["text"].strip() for p in pages) and mime == "application/pdf":
        raise ParseError("No readable text was found, including OCR")
    return pages


def main():
    # Linux worker limits are additional to Docker memory/CPU limits.
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024**2, 32 * 1024**2))
    try:
        result = parse_file(
            sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        )
        print(json.dumps({"pages": result}, ensure_ascii=False))
    except Exception as exc:
        # Never expose parser internals, paths or document contents.
        message = (
            str(exc)
            if isinstance(exc, ParseError)
            else "File parsing/OCR failed; check file integrity and OCR language installation"
        )
        print(json.dumps({"error": message}))
        sys.exit(1)


if __name__ == "__main__":
    main()
