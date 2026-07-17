from __future__ import annotations

from typing import Iterable


PAGE_SIZE_OPTIONS = (10, 25, 50, 60, 100)


def get_entries_per_page(request, param_name: str, default: int = 60) -> int:
    try:
        value = int(request.GET.get(param_name, default))
    except (TypeError, ValueError):
        return default

    return value if value in PAGE_SIZE_OPTIONS else default


def build_pagination_query(request, page_param: str) -> str:
    query_params = request.GET.copy()
    query_params.pop(page_param, None)
    return query_params.urlencode()


def get_page_range(paginator, page_number: int) -> Iterable:
    return list(paginator.get_elided_page_range(page_number))
