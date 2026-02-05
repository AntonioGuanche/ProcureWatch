"""
Download documents from URL to local path; stream to file and compute sha256.
"""
import hashlib
from pathlib import Path
from typing import Optional

import requests

# Map common content-type to file extension for local_path
CONTENT_TYPE_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    "application/x-pdf": "pdf",
    "text/plain": "txt",
    "text/html": "html",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


def infer_extension_from_content_type(content_type: Optional[str]) -> str:
    """Infer file extension from Content-Type header. Default 'bin'."""
    if not content_type:
        return "bin"
    base = content_type.split(";")[0].strip().lower()
    return CONTENT_TYPE_EXT.get(base, "bin")


def infer_extension_from_file_type_or_url(file_type: Optional[str], url: str = "") -> str:
    """Infer extension from document file_type or URL. For use before download."""
    if file_type:
        ext = file_type.strip().lower()
        if ext in ("pdf", "txt", "doc", "docx", "xls", "xlsx", "html"):
            return ext
        if ext == "application/pdf" or "pdf" in ext:
            return "pdf"
    if url:
        path = url.split("?")[0]
        if "." in path:
            return path.rsplit(".", 1)[-1].lower()[:10] or "bin"
    return "bin"


def download_document(
    url: str,
    dest_path: str | Path,
    timeout_seconds: int = 60,
) -> dict:
    """
    Download document from url to dest_path; stream to file and compute sha256.
    Returns metadata dict: content_type, sha256, file_size.
    Raises on request or IO errors (caller should record download_status=failed).
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    sha256_hash = hashlib.sha256()
    size = 0
    content_type: Optional[str] = None

    with requests.get(url, stream=True, timeout=timeout_seconds) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type") or "application/octet-stream"
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    sha256_hash.update(chunk)
                    size += len(chunk)
                    f.write(chunk)

    return {
        "content_type": (
            content_type.split(";")[0].strip() if content_type else "application/octet-stream"
        ),
        "sha256": sha256_hash.hexdigest(),
        "file_size": size,
    }
