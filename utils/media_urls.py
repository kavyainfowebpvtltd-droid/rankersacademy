from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.core.files.storage import default_storage


def upload_url(value, upload_dir=""):
    if not value:
        return ""

    name = getattr(value, "name", value)
    if not name:
        return ""

    normalized_name = str(name).replace("\\", "/").lstrip("/")
    if not normalized_name:
        return ""

    parsed = urlsplit(normalized_name)
    if parsed.scheme or parsed.netloc:
        return normalized_name

    if normalized_name.startswith("media/"):
        return "/" + normalized_name

    if normalized_name.startswith(("static/", "/static/", "/media/")):
        return normalized_name if normalized_name.startswith("/") else "/" + normalized_name

    upload_dir = str(upload_dir or "").strip("/").replace("\\", "/")
    candidates = [normalized_name]

    if upload_dir and "/" not in normalized_name:
        candidates.append(str(PurePosixPath(upload_dir) / normalized_name))

    selected_name = candidates[0]
    for candidate in candidates:
        if default_storage.exists(candidate):
            selected_name = candidate
            break
    else:
        if len(candidates) > 1:
            selected_name = candidates[-1]

    try:
        return default_storage.url(selected_name)
    except Exception:
        media_prefix = "/media/"
        return media_prefix + selected_name.lstrip("/")
