from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from urllib.parse import quote

from journey_api.config import get_settings
from journey_api.errors import ApiError


MAX_ATTACHMENT_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "text/plain": {".txt"},
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
}


def safe_original_filename(value: str, content_type: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        not normalized
        or len(normalized) > 180
        or normalized in {".", ".."}
        or normalized.startswith(".")
        or "/" in normalized
        or "\\" in normalized
        or any(unicodedata.category(char).startswith("C") for char in normalized)
    ):
        raise ApiError(422, "VALIDATION_FAILED", "附件文件名不安全，请重新命名后上传。")
    suffix = Path(normalized).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_TYPES.get(content_type, set()):
        raise ApiError(422, "VALIDATION_FAILED", "附件扩展名与内容类型不匹配。")
    return normalized


def validate_content(content: bytes, content_type: str) -> None:
    valid = False
    if content_type == "text/plain":
        try:
            content.decode("utf-8")
            valid = b"\x00" not in content
        except UnicodeDecodeError:
            valid = False
    elif content_type == "application/pdf":
        valid = content.startswith(b"%PDF-")
    elif content_type == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/jpeg":
        valid = content.startswith(b"\xff\xd8\xff")
    if not valid:
        raise ApiError(422, "VALIDATION_FAILED", "附件内容与声明的内容类型不匹配。")


def local_scan_clean(content: bytes) -> bool:
    # This deterministic local gate is intentionally not represented as a real AV scan.
    return b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" not in content


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


class LocalAttachmentStorage:
    def __init__(self) -> None:
        self.root = Path(get_settings().attachment_storage_root).resolve()

    def _path(self, storage_key: str) -> Path:
        if not storage_key.startswith("attachments/") or ".." in storage_key:
            raise ApiError(500, "DEPENDENCY_UNAVAILABLE", "附件存储引用无效。")
        path = (self.root / storage_key).resolve()
        if self.root not in path.parents:
            raise ApiError(500, "DEPENDENCY_UNAVAILABLE", "附件存储引用越界。")
        return path

    def put(self, storage_key: str, content: bytes) -> None:
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".uploading")
        temporary.write_bytes(content)
        temporary.replace(path)

    def get(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise ApiError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "附件存储暂不可用，请稍后重试。",
                retryable=True,
            ) from exc

    def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        path.unlink(missing_ok=True)


storage = LocalAttachmentStorage()
