import logging
import time

from django.conf import settings
from django.db import connection
from django.shortcuts import redirect
from django.urls import reverse

from .password_policy import user_needs_password_change

timing_logger = logging.getLogger("sds.request_timing")


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.perf_counter()
        queries = []
        response = None

        try:
            with connection.execute_wrapper(self._record_query_timing(queries)):
                response = self.get_response(request)
            return response
        finally:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            status_code = getattr(response, "status_code", 500)
            path = request.path
            watched_paths = getattr(settings, "REQUEST_TIMING_LOG_PATHS", set())
            is_watched_path = path in watched_paths or path.startswith("/scholarship/launch/")
            slow_request_ms = int(getattr(settings, "SLOW_REQUEST_MS", 1000))

            if is_watched_path or elapsed_ms >= slow_request_ms:
                queries = getattr(connection, "queries", [])[query_start_index:]
                timing_logger.info(
                    "request_timing path=%s method=%s status=%s duration_ms=%s query_count=%s",
                    path,
                    request.method,
                    status_code,
                    elapsed_ms,
                    len(queries),
                )

                slow_query_ms = int(getattr(settings, "SLOW_QUERY_MS", 250))
                for query in queries:
                    query_ms = query["duration_ms"]
                    if query_ms >= slow_query_ms:
                        timing_logger.warning(
                            "slow_query path=%s duration_ms=%s sql=%s",
                            path,
                            query_ms,
                            query["sql"],
                        )

    def _record_query_timing(self, queries):
        def wrapper(execute, sql, params, many, context):
            query_started_at = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                queries.append(
                    {
                        "duration_ms": int((time.perf_counter() - query_started_at) * 1000),
                        "sql": " ".join(str(sql).split()),
                    }
                )

        return wrapper


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
