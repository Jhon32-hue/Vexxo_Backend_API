# accounts/services/realtime_service.py
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def ping_account_changed(
    *,
    owner_id: int,
    account_id: int,
    event: str = "account.changed",
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Patrón 2: notificación liviana post-commit para UI/streaming.

    No enviamos el evento completo ni hacemos lógica crítica aquí.
    Solo avisamos: "la cuenta cambió". La UI luego consulta el nuevo balance
    por API o read-model.

    Implementación hoy: log.
    Implementación mañana: Redis pubsub / Django Channels / WS gateway.
    """
    payload = {
        "event": event,
        "owner_id": owner_id,
        "account_id": account_id,
        "extra": extra or {},
    }
    logger.info("[realtime] ping=%s", payload)