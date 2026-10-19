from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Cursor pagination stays fast on large tables and can't be used to count rows."""

    ordering = "-created_at"
    page_size = 50
    max_page_size = 200
    page_size_query_param = "page_size"
