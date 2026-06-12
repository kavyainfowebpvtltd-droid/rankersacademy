from .settings import *  # noqa: F401,F403


ROOT_URLCONF = "sds.urls"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
