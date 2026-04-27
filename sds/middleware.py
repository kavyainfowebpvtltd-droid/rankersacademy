from django.shortcuts import redirect
from django.urls import reverse

from .password_policy import user_needs_password_change


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and user_needs_password_change(request.user):
            force_change_path = reverse("force_password_change")
            logout_path = reverse("logout")
            exempt_prefixes = (
                force_change_path,
                logout_path,
                "/static/",
                "/media/",
            )

            if not any(request.path.startswith(prefix) for prefix in exempt_prefixes):
                return redirect("force_password_change")

        return self.get_response(request)
