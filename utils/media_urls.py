from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage


def _storage_exists(name):
    try:
        return default_storage.exists(name)
    except (SuspiciousFileOperation, ValueError):
        return False


def upload_url(value, upload_dirs=()):
    if not value:
        return ""

    name = getattr(value, "name", value)
    if not name:
        return ""

    normalized_name = str(name).replace("\\", "/").lstrip("/")
    if not normalized_name:
        return ""

    parsed = urlsplit(normalized_name)
    if parsed.scheme in ("http", "https") or parsed.netloc:
        return normalized_name

    local_path = parsed.path if parsed.scheme else normalized_name
    local_path = local_path.replace("\\", "/").lstrip("/")
    media_marker = "/media/"
    media_index = local_path.lower().rfind(media_marker)
    if media_index >= 0:
        normalized_name = local_path[media_index + len(media_marker):].lstrip("/")
    elif parsed.scheme:
        normalized_name = PurePosixPath(local_path).name

    if normalized_name.startswith("media/"):
        return "/" + normalized_name

    if normalized_name.startswith(("static/", "/static/", "/media/")):
        return normalized_name if normalized_name.startswith("/") else "/" + normalized_name

    candidates = [normalized_name]
    basename = PurePosixPath(normalized_name).name

    if isinstance(upload_dirs, str):
        upload_dirs = (upload_dirs,)
    upload_dirs = [
        str(upload_dir or "").strip("/").replace("\\", "/")
        for upload_dir in upload_dirs
        if str(upload_dir or "").strip("/")
    ]

    if basename and basename != normalized_name:
        candidates.append(basename)

    if basename:
        for upload_dir in upload_dirs:
            candidates.append(str(PurePosixPath(upload_dir) / basename))

    selected_name = candidates[0]
    for candidate in candidates:
        if _storage_exists(candidate):
            selected_name = candidate
            break

    try:
        return default_storage.url(selected_name)
    except Exception:
        media_prefix = "/media/"
        return media_prefix + selected_name.lstrip("/")
