"""
Dispatcher opcional de eventos de dominio hacia Google Cloud Pub/Sub.

Descripcion general:
- publica cada `MindwalletDomainEvent` en un topic de Pub/Sub
- se activa solo si la configuracion y dependencias estan disponibles

Analisis detallado:
- Vexxo conserva su bus local y su outbox como camino primario de
  consistencia; este dispatcher agrega distribucion externa para Cloud Run,
  Dataflow, analytics o integraciones desacopladas
- el dispatcher no conoce dominios concretos; solo serializa el contrato comun
  del evento y lo entrega a Pub/Sub
- si faltan credenciales, librerias o configuracion, simplemente no se
  registra y el sistema sigue funcionando localmente
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_REGISTERED = False


class PubSubDomainEventDispatcher:
    def __init__(
        self,
        *,
        project_id: str,
        topic_name: str,
        enable_ordering: bool = False,
        wait_for_result: bool = False,
        timeout_seconds: int = 5,
    ) -> None:
        self.project_id = project_id
        self.topic_name = topic_name
        self.enable_ordering = enable_ordering
        self.wait_for_result = wait_for_result
        self.timeout_seconds = timeout_seconds
        self._client = None
        self._topic_path = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client

        from google.cloud import pubsub_v1

        options = {}
        if self.enable_ordering:
            options["publisher_options"] = pubsub_v1.types.PublisherOptions(enable_message_ordering=True)

        self._client = pubsub_v1.PublisherClient(**options)
        self._topic_path = self._client.topic_path(self.project_id, self.topic_name)
        return self._client

    def __call__(self, event) -> None:
        client = self._ensure_client()
        payload = json.dumps(event.to_dict(), default=str).encode("utf-8")
        attributes = {
            "event_type": event.type,
            "context": event.context.value,
            "version": event.version,
            "priority": str(int(event.priority)),
            "source": str((event.metadata or {}).get("source", "")),
        }

        publish_kwargs = dict(data=payload, **attributes)
        if self.enable_ordering:
            publish_kwargs["ordering_key"] = event.context.value

        future = client.publish(self._topic_path, **publish_kwargs)
        if self.wait_for_result:
            future.result(timeout=self.timeout_seconds)


def _pubsub_ready() -> bool:
    return bool(
        getattr(settings, "DOMAIN_EVENTS_PUBSUB_ENABLED", False)
        and getattr(settings, "GCP_PROJECT_ID", "")
        and getattr(settings, "DOMAIN_EVENTS_PUBSUB_TOPIC", "")
    )


def register_pubsub_dispatcher(event_bus) -> bool:
    global _REGISTERED
    if _REGISTERED:
        return True

    if not _pubsub_ready():
        logger.info("[eventing] Pub/Sub dispatcher deshabilitado o incompleto.")
        return False

    try:
        __import__("google.cloud.pubsub_v1")
    except Exception:
        logger.warning(
            "[eventing] Pub/Sub habilitado por configuracion, pero falta la dependencia "
            "`google-cloud-pubsub`."
        )
        return False

    dispatcher = PubSubDomainEventDispatcher(
        project_id=settings.GCP_PROJECT_ID,
        topic_name=settings.DOMAIN_EVENTS_PUBSUB_TOPIC,
        enable_ordering=settings.DOMAIN_EVENTS_PUBSUB_ENABLE_ORDERING,
        wait_for_result=settings.DOMAIN_EVENTS_PUBSUB_WAIT_FOR_RESULT,
        timeout_seconds=settings.DOMAIN_EVENTS_PUBSUB_TIMEOUT_SECONDS,
    )
    event_bus.register_dispatcher(dispatcher)
    _REGISTERED = True
    logger.info(
        "[eventing] Dispatcher Pub/Sub registrado para topic=%s en project=%s.",
        settings.DOMAIN_EVENTS_PUBSUB_TOPIC,
        settings.GCP_PROJECT_ID,
    )
    return True
