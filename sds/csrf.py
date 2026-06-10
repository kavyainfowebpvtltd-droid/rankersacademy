from django.contrib.auth import get_user
from django.views.csrf import csrf_failure as default_csrf_failure


def csrf_failure(request, reason=""):
    """
    Recover from the common multi-tab login race.

    Django rotates the CSRF token after a successful login. If the same user has
    several login tabs open, later tabs can submit an old token and fail before
    the login view runs. When the session is already authenticated, redirect to
    the normal authenticated landing page instead of showing a 403.
    """
    is_login_post = request.method == "POST" and request.path in {"", "/"}
    is_bad_post_token = "CSRF token from POST" in str(reason or "")

    if is_login_post and is_bad_post_token:
        user = get_user(request)
        if getattr(user, "is_authenticated", False):
            from .views import _redirect_authenticated_user_home

            return _redirect_authenticated_user_home(user)

    return default_csrf_failure(request, reason=reason)
