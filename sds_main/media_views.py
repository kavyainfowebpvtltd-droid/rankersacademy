from pathlib import PurePosixPath

from django.conf import settings
from django.http import Http404
from django.views.static import serve


PROFILE_MEDIA_DIRS = (
    "student_profiles",
    "student_profile",
    "teacher_profiles",
    "teacher_profile",
)


def serve_media(request, path):
    normalized_path = str(path or "").replace("\\", "/").lstrip("/")
    if not normalized_path or ".." in PurePosixPath(normalized_path).parts:
        raise Http404("Media file not found")

    try:
        return serve(request, normalized_path, document_root=settings.MEDIA_ROOT)
    except Http404:
        pass

    basename = PurePosixPath(normalized_path).name
    candidates = []

    if basename and basename != normalized_path:
        candidates.append(basename)

    if basename:
        for media_dir in PROFILE_MEDIA_DIRS:
            candidates.append(str(PurePosixPath(media_dir) / basename))

    for candidate in dict.fromkeys(candidates):
        try:
            return serve(request, candidate, document_root=settings.MEDIA_ROOT)
        except Http404:
            continue

    raise Http404("Media file not found")
