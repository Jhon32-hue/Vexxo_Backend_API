from __future__ import annotations
# Servicio para enriquecer alertas con IA (LLMs). Recién implementado como stub.

import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from alerts.alerts.models.alerts import Alert, AlertCategory, AlertSeverity
from common.domain_events import publish_domain_event, EventNames, EventContext
from identity.users.services.product_access_service import allow_ai_request

logger = logging.getLogger(__name__)


# ========= CONFIG & HELPERS DE ENTORNO =========

def _is_ai_enrichment_enabled() -> bool:
    """
    Flag central para activar / desactivar el enriquecimiento por IA.

    Útil para:
    - entornos de desarrollo / tests
    - tenants / planes sin IA
    """
    return bool(getattr(settings, "ALERTS_AI_ENABLED", True))


def _get_user_locale(alert: Alert) -> str:
    """
    Devuelve el idioma preferido del usuario, si lo tienes en algún perfil.
    Fallback a 'es' (Vexxo_app Colombia/Latam).
    """
    user = alert.owner
    # Si en algún momento usamos user.profile.language o settings propios:
    for attr in ("language", "locale", "preferred_locale"):
        val = getattr(getattr(user, "profile", None), attr, None)
        if val:
            return val

    return "es"  # idioma por defecto


# ========= CONSTRUCCIÓN DEL "PROMPT" (ABSTRACCIÓN) =========


def _build_alert_ai_payload(alert: Alert, correlation_id: Optional[str]) -> Dict[str, Any]:
    """
    Se construye la estructura que se le mandaría a un LLM.

    Aquí NO se formatea el prompt como string gigante; dejamos
    un dict rico que un "provider" luego serializa como quiera.
    """
    return {
        "meta": {
            "correlation_id": correlation_id,
            "alert_id": alert.pk,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "source": alert.source,
            "type": alert.type,
            "category": alert.category,
            "severity": alert.severity,
        },
        "user": {
            "id": alert.owner_id,
            "locale": _get_user_locale(alert),
        },
        "content": {
            "title": alert.title,
            "message": alert.message,
            "payload": alert.payload or {},
        },
        "now": timezone.now().isoformat(),
        "context_hints": [
            "Vexxo_app es una aplicación de finanzas personales.",
            "Esta aplicación ayuda a usuarios a centralizar, normalizar, interpretar, optimizar y ejecutar acciones sobre sus finanzas.",
            "El usuario es una persona, freelancer o pyme, no un banco. Por tanto, la comunicación debe ser cercana y empática.",
            "También, la explicación debe ser clara, empática y accionable para evitar confusiones.",
        ],
    }


# ========= PROVIDER ABSTRACTION (STUB) =========


def _call_llm_provider(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Punto único donde, en el futuro, llamamos a un proveedor de IA.

    Por ahora es un stub "inteligente":
    - Genera un resumen y tags basados en categoría/severidad.
    - Se puede reemplazar este cuerpo por una llamada real a OpenAI, Anthropic, etc.
    """
    category = payload["meta"].get("category") or AlertCategory.OTHER
    severity = payload["meta"].get("severity") or AlertSeverity.MEDIUM
    content = payload["content"]
    locale = payload["user"].get("locale", "es")

    title = content.get("title") or ""
    raw_type = payload["meta"].get("type") or "alert"

    # Base del resumen según categoría
    if locale.startswith("es"):
        base_prefix = {
            AlertCategory.SPENDING: "Se ha detectado un evento relacionado con tus gastos.",
            AlertCategory.CASHFLOW: "Hay un evento importante en tu flujo de caja.",
            AlertCategory.GOAL: "Esta alerta está relacionada con tus metas financieras.",
            AlertCategory.DEBT: "Hay un movimiento vinculado a tus deudas o préstamos.",
            AlertCategory.RISK: "Se ha identificado un posible riesgo en tus finanzas.",
            AlertCategory.SYSTEM: "Se ha generado una alerta técnica del sistema.",
            AlertCategory.OTHER: "Se ha generado una alerta en tu cuenta.",
        }.get(category, "Se ha generado una alerta en tu cuenta.")
    else:
        base_prefix = {
            AlertCategory.SPENDING: "A spending-related event has been detected.",
            AlertCategory.CASHFLOW: "An important cashflow event occurred.",
            AlertCategory.GOAL: "This alert is related to your financial goals.",
            AlertCategory.DEBT: "There is an event linked to your debts or loans.",
            AlertCategory.RISK: "A potential risk in your finances was identified.",
            AlertCategory.SYSTEM: "A technical/system alert has been generated.",
            AlertCategory.OTHER: "An alert was generated in your account.",
        }.get(category, "An alert was generated in your account.")

    # Matiz según severidad
    if locale.startswith("es"):
        severity_suffix = {
            AlertSeverity.LOW: "No parece urgente, pero vale la pena que le eches un vistazo.",
            AlertSeverity.MEDIUM: "Es recomendable que revises esta situación pronto.",
            AlertSeverity.HIGH: "Revisa esta situación cuanto antes para evitar problemas.",
            AlertSeverity.CRITICAL: "Es una alerta crítica; actúa de inmediato si es posible.",
        }.get(severity, "Revisa esta situación cuando te sea posible.")
    else:
        severity_suffix = {
            AlertSeverity.LOW: "It does not look urgent but worth checking.",
            AlertSeverity.MEDIUM: "You should review this situation soon.",
            AlertSeverity.HIGH: "You should check this as soon as possible.",
            AlertSeverity.CRITICAL: "This is a critical alert; act immediately if you can.",
        }.get(severity, "Review this situation when you can.")

    # Pequeño resumen contextual
    if locale.startswith("es"):
        summary = f"{base_prefix} {severity_suffix}"
        if title:
            summary += f" ({title})"
    else:
        summary = f"{base_prefix} {severity_suffix}"
        if title:
            summary += f" ({title})"

    # Tags base
    tags: List[str] = []

    # Por categoría
    if category == AlertCategory.SPENDING:
        tags.extend(["spending", "budget", "cash_out"])
    elif category == AlertCategory.CASHFLOW:
        tags.extend(["cashflow", "inflow_outflow"])
    elif category == AlertCategory.GOAL:
        tags.extend(["goal", "progress"])
    elif category == AlertCategory.DEBT:
        tags.extend(["debt", "liability"])
    elif category == AlertCategory.RISK:
        tags.extend(["risk", "anomaly"])
    elif category == AlertCategory.SYSTEM:
        tags.extend(["system", "tech"])
    else:
        tags.append("generic")

    # Por severidad
    tags.append(f"severity_{severity.lower()}")

    # Tag de origen IA
    tags.append("ai_enriched")

    # Risk score heurístico según severidad
    base_risk_by_severity = {
        AlertSeverity.LOW: 30,
        AlertSeverity.MEDIUM: 50,
        AlertSeverity.HIGH: 70,
        AlertSeverity.CRITICAL: 90,
    }
    risk_score = base_risk_by_severity.get(severity, 50)

    return {
        "ai_summary": summary,
        "risk_score": risk_score,
        "ai_tags": tags,
        "raw_output": {...}  # respuesta cruda del LLM
    }


# ========= API PÚBLICA =========


def enrich_alert_with_ai(alert: Alert, correlation_id: Optional[str] = None) -> None:
    """
    Punto único para integrar LLMs en el futuro.

    Flujo actual (stub):
    1) Verifica si la IA está habilitada.
    2) Construye un payload rico con contexto de Vexxo_app.
    3) Llama al provider stub.
    4) Actualiza ai_summary, risk_score, ai_tags en la alerta.
    5) Publica ALERT_AI_ENRICHED para que otros módulos reaccionen.
    """
    if not _is_ai_enrichment_enabled():
        logger.debug(
            "[alerts.ai] IA deshabilitada; alerta id=%s no será enriquecida (corr=%s)",
            alert.pk,
            correlation_id,
        )
        return

    if not allow_ai_request(
        alert.owner,
        source="alerts.ai.enrich_alert_with_ai",
        feature=f"alert:{alert.type}",
    ):
        logger.info(
            "[alerts.ai] Limite de IA alcanzado para user_id=%s alert_id=%s",
            alert.owner_id,
            alert.pk,
        )
        return

    try:
        payload = _build_alert_ai_payload(alert, correlation_id=correlation_id)

        #  FUTURO (proveedor real):
        #  llm_result = external_llm_client.generate_alert_insight(payload)
        #  Otra opción: se publica un evento y un worker asíncrono procesa la llamada LLM.
        #
        #  publish_domain_event(
        #      EventNames.ALERT_CREATED,
        #      context=EventContext.ALERTS,
        #      payload=payload,
        #  )
        #  # Un microservicio llm_service escucha ese evento vía Kafka,
        #  # genera insight y llama a:
        #  #   PATCH /alerts/{id}/enrich/
        #  # para actualizar ai_summary, risk_score, ai_tags.
        #
        #  En ese escenario, este método podría reducirse a solo preparar
        #  el payload y publicar el evento.

        llm_result = _call_llm_provider(payload)

        # opcional: guardar salida cruda para debugging
        raw_output = llm_result.get("raw_output")
        if raw_output:
            alert.payload = alert.payload or {}
            alert.payload["llm_raw"] = raw_output

        ai_summary = llm_result.get("ai_summary") or alert.ai_summary
        risk_score = llm_result.get("risk_score", alert.risk_score)
        new_tags = llm_result.get("ai_tags", []) or []

        # Mezclamos tags antiguas con nuevas, sin duplicados
        existing_tags = alert.ai_tags or []
        merged_tags = list({*existing_tags, *new_tags})

        alert.ai_summary = ai_summary
        alert.risk_score = risk_score
        alert.ai_tags = merged_tags

        # Guardamos cambios (una sola vez)
        update_fields = ["ai_summary", "risk_score", "ai_tags", "updated_at"]
        if raw_output:
            update_fields.append("payload")

        alert.save(update_fields=update_fields)

        logger.debug(
            "[alerts.ai] Alerta id=%s enriquecida con IA (dummy/provider) corr=%s",
            alert.pk,
            correlation_id,
        )

        #  publicamos evento de enriquecimiento IA
        publish_domain_event(
            event_type=EventNames.ALERT_AI_ENRICHED,
            context=EventContext.ALERTS,
            payload={
                "alert_id": alert.pk,
                "owner_id": alert.owner_id,
                "risk_score": alert.risk_score,
                "ai_tags": alert.ai_tags,
                "category": alert.category,
                "severity": alert.severity,
                "type": alert.type,
            },
            metadata={
                "source": "alerts.ai_services",
                "correlation_id": correlation_id,
                "projection_event_key": f"alert-ai:{alert.pk}",
            },
        )

        # ================== EJEMPLOS DE USO FUTURO (CON ESTE EVENTO) ==================
        #
        # 1) Actualizar dashboards
        #
        #   @subscribe(EventNames.ALERT_AI_ENRICHED, name="dashboards.on_alert_ai")
        #   def on_alert_ai(event: VexxoAppDomainEvent):
        #       # recalcular KPIs y refrescar widgets para ese usuario
        #       # (por ejemplo, emitir un WebSocket o notificación interna)
        #       ...
        #
        # 2) Notificar al usuario
        #
        #   @subscribe(EventNames.ALERT_AI_ENRICHED, name="notifications.on_alert_ai")
        #   def notify_user(event: VexxoAppDomainEvent):
        #       # usar event.payload["alert_id"] y ["owner_id"]
        #       # para enviar push/email/WhatsApp con alert.ai_summary
        #       ...
        #
        # 3) Generar insights secundarios
        #
        #   @subscribe(EventNames.ALERT_AI_ENRICHED, name="insights.on_alert_ai")
        #   def build_secondary_insights(event: VexxoAppDomainEvent):
        #       # alimentar un modelo que agrupa alertas y genera historias:
        #       # "este mes gastaste más en transporte, comida, etc."
        #       ...
        #
        # 4) Alimentar un “CFO virtual”
        #
        #   @subscribe(EventNames.ALERT_AI_ENRICHED, name="cfo_virtual.on_alert_ai")
        #   def cfo_reasoning(event: VexxoAppDomainEvent):
        #       # combinar alertas enriquecidas + transacciones + budgets
        #       # para generar recomendaciones tipo:
        #       # "baja tus gastos recurrentes en X"
        #       # "estás cerca de tu meta Y, podrías aportar Z"
        #       ...

    except Exception as e:
        logger.error(
            "[alerts.ai] Error enriqueciendo alerta id=%s corr=%s: %s",
            alert.pk,
            correlation_id,
            e,
            exc_info=True,
        )
        # En caso de error NO publicamos ALERT_AI_ENRICHED
