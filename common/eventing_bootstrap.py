"""
Bootstrap central del bus de eventos y dispatchers externos.

Descripcion general:
- registra dispatchers opcionales del event bus global
- mantiene el flujo local actual y solo agrega salidas cloud cuando estan
  configuradas

Analisis detallado:
- Vexxo ya usa un bus local con outbox; este bootstrap no reemplaza nada, solo
  enchufa dispatchers externos como Pub/Sub
- debe ser idempotente porque `AppConfig.ready()` puede ejecutarse mas de una
  vez en ciertos entornos
- cualquier fallo de bootstrap se loggea, pero no debe tumbar el arranque del
  proyecto
"""

from __future__ import annotations

import logging

from common.domain_events import event_bus

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False


def bootstrap_domain_eventing() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    _BOOTSTRAPPED = True

    try:
        from common.gcp.pubsub_dispatcher import register_pubsub_dispatcher

        register_pubsub_dispatcher(event_bus)
    except Exception:
        logger.exception("[eventing] No se pudo registrar el dispatcher de Pub/Sub.")
