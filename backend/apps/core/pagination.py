from urllib.parse import urlsplit

from rest_framework.pagination import PageNumberPagination


def _relative(link):
    if not link:
        return link
    parts = urlsplit(link)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


class SamPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_next_link(self):
        return _relative(super().get_next_link())

    def get_previous_link(self):
        return _relative(super().get_previous_link())

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {"type": "integer", "example": 42},
                "next": {
                    "type": "string",
                    "nullable": True,
                    "example": "/api/attendances/?page=2",
                },
                "previous": {"type": "string", "nullable": True, "example": None},
                "results": schema,
            },
        }
