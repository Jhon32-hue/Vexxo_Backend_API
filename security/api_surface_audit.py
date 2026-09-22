from __future__ import annotations

from django.urls import URLPattern, URLResolver, get_resolver
import ast
from pathlib import Path

from django.conf import settings


def _patterns(patterns, prefix=""):
    for pattern in patterns:
        route = f"{prefix}{pattern.pattern}"
        if isinstance(pattern, URLResolver):
            yield from _patterns(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern):
            yield route, pattern.callback


def audit_api_surfaces() -> dict:
    rows = []
    seen = set()
    for route, callback in _patterns(get_resolver().url_patterns):
        view_class = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
        if view_class is None:
            continue
        key = (view_class.__module__, view_class.__name__)
        if key in seen:
            continue
        seen.add(key)
        filterset = getattr(view_class, "filterset_fields", ()) or ()
        ordering = getattr(view_class, "ordering_fields", ()) or ()
        search = getattr(view_class, "search_fields", ()) or ()
        issues = []
        if filterset == "__all__" or ordering == "__all__":
            issues.append("wildcard_fields")
        backends = [backend.__name__ for backend in (getattr(view_class, "filter_backends", ()) or ())]
        if "OrderingFilter" in backends and not ordering:
            issues.append("ordering_without_allowlist")
        rows.append({
            "view": f"{key[0]}.{key[1]}", "sample_route": route,
            "filterset_fields": list(filterset) if not isinstance(filterset, str) else filterset,
            "ordering_fields": list(ordering) if not isinstance(ordering, str) else ordering,
            "search_fields": list(search), "issues": issues,
        })
    code_findings = _audit_dynamic_query_code()
    issues = [row for row in rows if row["issues"]]
    return {
        "view_count": len(rows),
        "unsafe_view_count": len(issues),
        "unsafe_code_count": len(code_findings),
        "code_findings": code_findings,
        "views": rows,
    }


def _audit_dynamic_query_code() -> list[dict]:
    findings = []
    root = Path(settings.BASE_DIR)
    for path in root.rglob("*.py"):
        if any(part in {"migrations", ".venv", "venv", "__pycache__"} for part in path.parts) or path.name.startswith("test"):
            continue
        if path.as_posix().endswith("security/query_safety.py"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            issue = ""
            if method in {"raw", "extra"}:
                issue = f"manual_queryset_{method}"
            elif method == "order_by" and any(not isinstance(arg, ast.Constant) for arg in node.args):
                issue = "dynamic_order_by_requires_validate_ordering"
            elif method == "get" and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "query_params":
                if not node.args or not isinstance(node.args[0], ast.Constant):
                    issue = "dynamic_query_parameter_name"
            if issue:
                findings.append({"file": str(path.relative_to(root)).replace("\\", "/"), "line": node.lineno, "issue": issue})
    return findings
