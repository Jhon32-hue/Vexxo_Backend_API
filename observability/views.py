from django.http import JsonResponse
from django.views.decorators.http import require_GET

from observability.healthchecks import runtime_health


@require_GET
def liveness_view(request):
    return JsonResponse({"ok": True, "service": "vexxo-backend"})


@require_GET
def readiness_view(request):
    payload = runtime_health()
    return JsonResponse(payload, status=200 if payload["ok"] else 503)
