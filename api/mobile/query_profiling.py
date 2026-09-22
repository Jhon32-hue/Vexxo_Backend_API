import hashlib
import json
import re
from collections import defaultdict
from time import perf_counter

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient


_LITERAL_PATTERN = re.compile(r"'(?:''|[^'])*'|\b\d+(?:\.\d+)?\b")
_SPACE_PATTERN = re.compile(r"\s+")


def fingerprint_sql(sql: str) -> tuple[str, str]:
    normalized = _SPACE_PATTERN.sub(" ", _LITERAL_PATTERN.sub("?", sql)).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return digest, normalized[:240]


def profile_mobile_endpoint(
    *,
    user,
    endpoint: str,
    top: int = 10,
    section_versions: dict[str, str] | None = None,
) -> dict:
    path = f"/api/mobile/{endpoint}/"
    client = APIClient()
    client.force_authenticate(user=user)

    started_at = perf_counter()
    with CaptureQueriesContext(connection) as captured:
        headers = {}
        if section_versions is not None:
            headers["HTTP_X_VEXXO_MOBILE_SECTION_VERSIONS"] = json.dumps(section_versions)
        response = client.get(path, HTTP_HOST="localhost", **headers)
    request_time_ms = (perf_counter() - started_at) * 1000

    grouped = defaultdict(lambda: {"count": 0, "time_ms": 0.0, "sql": ""})
    total_time_ms = 0.0
    for query in captured.captured_queries:
        digest, normalized = fingerprint_sql(query["sql"])
        elapsed_ms = float(query.get("time") or 0) * 1000
        total_time_ms += elapsed_ms
        grouped[digest]["count"] += 1
        grouped[digest]["time_ms"] += elapsed_ms
        grouped[digest]["sql"] = normalized

    repeated = [
        {"fingerprint": key, **value}
        for key, value in grouped.items()
        if value["count"] > 1
    ]
    repeated.sort(key=lambda item: (item["count"], item["time_ms"]), reverse=True)
    response_sections = getattr(response, "data", {}).get("sections", {})
    return {
        "endpoint": path,
        "status_code": response.status_code,
        "query_count": len(captured),
        "database_time_ms": round(total_time_ms, 3),
        "request_time_ms": round(request_time_ms, 3),
        "repeated_query_groups": repeated[: max(top, 0)],
        "section_versions": {
            key: str(value.get("version", ""))
            for key, value in response_sections.items()
            if isinstance(value, dict)
        },
    }
