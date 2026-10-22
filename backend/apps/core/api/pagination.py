"""Pagination configurations for AMAPP historical and analytical endpoints."""

from __future__ import annotations

from rest_framework.pagination import LimitOffsetPagination


class AMAPPHistoryPagination(LimitOffsetPagination):
    """Standard limit-offset pagination for historical run, benchmark, and metric queries.

    Enforces bounded limits [1, 100] with default page limit of 20 items to prevent
    unbounded database scans and excessive payload serialization.
    """

    default_limit = 20
    max_limit = 100
    limit_query_param = "limit"
    offset_query_param = "offset"
