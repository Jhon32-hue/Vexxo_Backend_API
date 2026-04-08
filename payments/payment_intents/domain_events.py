"""
Contratos y builders de eventos del bounded context `payments.payment_intents`.

Descripcion general:
- centraliza nombres, payloads base y catalogo operativo del dominio de pagos
- evita que vistas, callbacks, workers y servicios inventen estructuras
  incompatibles

Analisis detallado:
- `payments` ya tiene outbox propio; este archivo define el contrato del
  dominio, no el transporte
- los eventos aqui definidos deben poder viajar por bus local, outbox,
  Pub/Sub, Cloud Tasks o workers de Cloud Run sin cambiar su semantica
- ademas de los eventos fuertes de dominio, `payments` puede complementar la UX
  con senales realtime livianas sin reemplazar ni duplicar el outbox
"""

from __future__ import annotations

from common.domain_events import EventNames


def _stringify_id(value) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


class PaymentDomainEventTypes:
    PAYMENT_ORDER_REQUESTED = EventNames.PAYMENT_ORDER_REQUESTED
    PAYMENT_INTENT_CREATED = EventNames.PAYMENT_INTENT_CREATED
    PAYMENT_INTENT_DISPATCHED = EventNames.PAYMENT_INTENT_DISPATCHED
    PAYMENT_INTENT_REQUIRES_ACTION = EventNames.PAYMENT_INTENT_REQUIRES_ACTION
    PAYMENT_INTENT_PROCESSING = EventNames.PAYMENT_INTENT_PROCESSING
    PAYMENT_INTENT_SUCCEEDED = EventNames.PAYMENT_INTENT_SUCCEEDED
    PAYMENT_INTENT_FAILED = EventNames.PAYMENT_INTENT_FAILED
    PAYMENT_INTENT_CANCELLED = EventNames.PAYMENT_INTENT_CANCELLED
    PAYMENT_INTENT_SETTLED = EventNames.PAYMENT_INTENT_SETTLED
    PAYMENT_INTENT_REVERSED = EventNames.PAYMENT_INTENT_REVERSED
    PAYMENT_INTENT_DISPUTED = EventNames.PAYMENT_INTENT_DISPUTED
    PAYMENT_FEE_CALCULATED = EventNames.PAYMENT_FEE_CALCULATED
    PAYMENT_PROVIDER_REFERENCE_RECORDED = EventNames.PAYMENT_PROVIDER_REFERENCE_RECORDED
    PAYMENT_CALLBACK_RECEIVED = EventNames.PAYMENT_CALLBACK_RECEIVED
    PAYMENT_SETTLEMENT_RECORDED = EventNames.PAYMENT_SETTLEMENT_RECORDED
    PAYMENT_RECURRING_TEMPLATE_CREATED = EventNames.PAYMENT_RECURRING_TEMPLATE_CREATED
    PAYMENT_RECURRING_TEMPLATE_UPDATED = EventNames.PAYMENT_RECURRING_TEMPLATE_UPDATED
    PAYMENT_RECURRING_RUN_REQUESTED = EventNames.PAYMENT_RECURRING_RUN_REQUESTED
    PAYMENT_PAYOUT_REQUESTED = EventNames.PAYMENT_PAYOUT_REQUESTED
    PAYMENT_PAYOUT_SUCCEEDED = EventNames.PAYMENT_PAYOUT_SUCCEEDED
    PAYMENT_PAYOUT_FAILED = EventNames.PAYMENT_PAYOUT_FAILED


PAYMENT_EVENT_CATALOG = [
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_ORDER_REQUESTED,
        "category": "command",
        "description": "Se emite cuando el usuario solicita iniciar un pago externo.",
        "emitted_by": ["payments.payment_intents.services.create_payment_intent"],
        "current_local_listeners": [],
        "intended_consumers": ["integrations", "workers", "audit"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_CREATED,
        "category": "lifecycle",
        "description": "Se emite al persistir el intent canónico previo al PSP.",
        "emitted_by": ["payments.payment_intents.services.create_payment_intent"],
        "current_local_listeners": ["payments.publish_intent_created_realtime_signal"],
        "intended_consumers": ["integrations", "usage_projection", "analytics", "ui"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_DISPATCHED,
        "category": "lifecycle",
        "description": "Se emite cuando el intent se envía al rail o proveedor.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_dispatched"],
        "current_local_listeners": ["payments.publish_intent_dispatched_realtime_signal"],
        "intended_consumers": ["ui", "integrations", "observability"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_REQUIRES_ACTION,
        "category": "lifecycle",
        "description": "Se emite cuando el proveedor exige accion adicional del usuario.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_requires_action"],
        "current_local_listeners": [
            "payments.publish_intent_requires_action_realtime_signal",
            "notifications.handle_payment_intent_requires_action",
        ],
        "intended_consumers": ["ui", "notifications", "support"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_PROCESSING,
        "category": "lifecycle",
        "description": "Se emite cuando el pago entra en procesamiento externo.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_processing"],
        "current_local_listeners": ["payments.publish_intent_processing_realtime_signal"],
        "intended_consumers": ["ui", "observability"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_SUCCEEDED,
        "category": "lifecycle",
        "description": "Se emite cuando el proveedor confirma ejecucion exitosa.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_succeeded"],
        "current_local_listeners": ["payments.publish_intent_succeeded_realtime_signal"],
        "intended_consumers": ["transactions", "ui", "analytics", "notifications"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_FAILED,
        "category": "lifecycle",
        "description": "Se emite cuando el pago falla.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_failed"],
        "current_local_listeners": [
            "payments.publish_intent_failed_realtime_signal",
            "notifications.handle_payment_intent_failed",
        ],
        "intended_consumers": ["ui", "support", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_CANCELLED,
        "category": "lifecycle",
        "description": "Se emite cuando el pago se cancela.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_cancelled"],
        "current_local_listeners": ["payments.publish_intent_cancelled_realtime_signal"],
        "intended_consumers": ["ui", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_SETTLED,
        "category": "settlement",
        "description": "Se emite cuando el pago queda liquidado externamente.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_settled"],
        "current_local_listeners": ["payments.publish_intent_settled_realtime_signal"],
        "intended_consumers": ["transactions", "reconciliation", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_REVERSED,
        "category": "operational_case",
        "description": "Se emite cuando el proveedor informa una reversa.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_reversed"],
        "current_local_listeners": ["payments.publish_intent_reversed_realtime_signal"],
        "intended_consumers": ["support", "risk", "transactions", "ui"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_INTENT_DISPUTED,
        "category": "operational_case",
        "description": "Se emite cuando el pago entra en disputa.",
        "emitted_by": ["payments.payment_intents.services.mark_payment_intent_disputed"],
        "current_local_listeners": ["payments.publish_intent_disputed_realtime_signal"],
        "intended_consumers": ["support", "risk", "ui"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_FEE_CALCULATED,
        "category": "pricing",
        "description": "Se emite cuando se calcula pricing estimado del pago.",
        "emitted_by": ["payments.payment_intents.services.create_payment_intent"],
        "current_local_listeners": [],
        "intended_consumers": ["analytics", "pricing_observability"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_PROVIDER_REFERENCE_RECORDED,
        "category": "provider",
        "description": "Se emite al registrar referencias operativas del proveedor.",
        "emitted_by": ["payments.payment_intents.services.record_payment_provider_reference"],
        "current_local_listeners": [],
        "intended_consumers": ["support", "reconciliation", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_CALLBACK_RECEIVED,
        "category": "provider",
        "description": "Se emite cuando Vexxo recibe y procesa un callback del proveedor.",
        "emitted_by": ["payments.payment_intents.callback_service.process_payment_provider_callback"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "support", "observability"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_SETTLEMENT_RECORDED,
        "category": "settlement",
        "description": "Se emite al registrar un settlement reconciliable.",
        "emitted_by": ["payments.payment_intents.callback_service.process_payment_provider_callback"],
        "current_local_listeners": [],
        "intended_consumers": ["reconciliation", "analytics", "support"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_CREATED,
        "category": "planning",
        "description": "Se emite al crear un template recurrente/programado.",
        "emitted_by": ["payments.scheduled_payments.services.create_payment_template"],
        "current_local_listeners": [],
        "intended_consumers": ["scheduler", "ui", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_UPDATED,
        "category": "planning",
        "description": "Se emite al actualizar un template recurrente/programado.",
        "emitted_by": ["payments.scheduled_payments.services.update_payment_template"],
        "current_local_listeners": [],
        "intended_consumers": ["scheduler", "ui", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_RECURRING_RUN_REQUESTED,
        "category": "planning",
        "description": "Se emite al pedir una corrida de pago programado.",
        "emitted_by": ["payments.scheduled_payments.services.request_payment_schedule_run"],
        "current_local_listeners": [],
        "intended_consumers": ["scheduler", "workers", "analytics"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_PAYOUT_REQUESTED,
        "category": "payout",
        "description": "Se emite al registrar una dispersion o instruccion de salida.",
        "emitted_by": [
            "payments.payment_intents.payout_service.create_payout_batch",
            "payments.payment_intents.payout_service.add_payout_instruction",
        ],
        "current_local_listeners": ["payments.publish_payout_requested_realtime_signal"],
        "intended_consumers": ["integrations", "usage_projection", "analytics", "ui"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_PAYOUT_SUCCEEDED,
        "category": "payout",
        "description": "Se emite al confirmar una instruccion de dispersion exitosa.",
        "emitted_by": ["payments.payment_intents.payout_service.mark_payout_instruction_succeeded"],
        "current_local_listeners": ["payments.publish_payout_succeeded_realtime_signal"],
        "intended_consumers": ["ui", "analytics", "support"],
    },
    {
        "event_type": PaymentDomainEventTypes.PAYMENT_PAYOUT_FAILED,
        "category": "payout",
        "description": "Se emite al fallar una instruccion de dispersion.",
        "emitted_by": ["payments.payment_intents.payout_service.mark_payout_instruction_failed"],
        "current_local_listeners": ["payments.publish_payout_failed_realtime_signal"],
        "intended_consumers": ["ui", "support", "analytics"],
    },
]


PAYMENT_EVENT_GOVERNANCE = {
    "default": {
        "contract_status": "active",
        "schema_version": "v1",
        "deprecated": False,
        "deprecated_by": None,
        "visibility": "internal",
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_CREATED: {
        "payload_fields": [
            "payment_intent_id",
            "owner_id",
            "payment_type",
            "rail",
            "status",
            "provider",
            "amount",
            "currency",
            "internal_reference",
            "external_reference",
            "pricing_snapshot",
            "fee_breakdown",
            "tax_breakdown",
            "change",
            "usage_transition",
        ],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "amount", "currency", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_DISPATCHED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "provider_intent_id", "status", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_REQUIRES_ACTION: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_PROCESSING: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_SUCCEEDED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "provider_reference", "provider_cus", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_SETTLED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "provider_reference", "provider_cus", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_FAILED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "failure_code", "failure_message", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_CANCELLED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "failure_message", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_REVERSED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "failure_message", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_INTENT_DISPUTED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "status", "failure_message", "change", "usage_transition"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "status", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_FEE_CALCULATED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "rail", "payment_type", "amount", "currency", "pricing_snapshot"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "amount", "currency", "pricing_snapshot"],
    },
    PaymentDomainEventTypes.PAYMENT_PROVIDER_REFERENCE_RECORDED: {
        "payload_fields": ["payment_intent_id", "owner_id", "provider", "provider_reference", "provider_cus", "change"],
        "required_fields": ["payment_intent_id", "owner_id", "provider", "change"],
    },
    PaymentDomainEventTypes.PAYMENT_CALLBACK_RECEIVED: {
        "payload_fields": ["provider", "receipt_id", "payment_intent_id", "status", "issue_kind"],
        "required_fields": ["provider", "receipt_id"],
    },
    PaymentDomainEventTypes.PAYMENT_SETTLEMENT_RECORDED: {
        "payload_fields": ["payment_intent_id", "settlement_id", "provider", "rail", "amount", "settlement_reference"],
        "required_fields": ["payment_intent_id", "settlement_id", "provider", "amount"],
    },
    PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_CREATED: {
        "payload_fields": ["template_id", "owner_id", "payment_type", "cadence", "is_active"],
        "required_fields": ["template_id", "owner_id", "payment_type", "cadence"],
    },
    PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_UPDATED: {
        "payload_fields": ["template_id", "owner_id", "payment_type", "cadence", "is_active"],
        "required_fields": ["template_id", "owner_id", "payment_type", "cadence"],
    },
    PaymentDomainEventTypes.PAYMENT_RECURRING_RUN_REQUESTED: {
        "payload_fields": ["schedule_run_id", "template_id", "owner_id", "scheduled_for", "payment_type"],
        "required_fields": ["schedule_run_id", "template_id", "owner_id", "scheduled_for"],
    },
    PaymentDomainEventTypes.PAYMENT_PAYOUT_REQUESTED: {
        "payload_fields": ["instruction_id", "batch_id", "owner_id", "provider", "rail", "amount", "currency", "usage_transition"],
        "required_fields": ["batch_id", "owner_id", "provider"],
    },
    PaymentDomainEventTypes.PAYMENT_PAYOUT_SUCCEEDED: {
        "payload_fields": ["instruction_id", "batch_id", "owner_id", "amount", "currency", "provider_reference", "provider_cus", "usage_transition"],
        "required_fields": ["instruction_id", "batch_id", "owner_id", "amount", "currency"],
    },
    PaymentDomainEventTypes.PAYMENT_PAYOUT_FAILED: {
        "payload_fields": ["instruction_id", "batch_id", "owner_id", "amount", "currency", "failure_code", "failure_message", "usage_transition"],
        "required_fields": ["instruction_id", "batch_id", "owner_id", "amount", "currency"],
    },
}


def get_payment_event_governance() -> dict:
    return {
        "versioning_policy": {
            "event_name_format": "bounded_context.resource.action.vN",
            "breaking_changes": "create_new_version",
            "non_breaking_changes": "append_optional_fields_only",
        },
        "deprecation_policy": {
            "supported_statuses": ["active", "deprecated", "internal_only"],
            "default_status": "active",
            "removal_rule": "deprecate_before_removal",
        },
        "schema_registry_style": "lightweight_inline_registry",
        "registry": {
            event_type: {**PAYMENT_EVENT_GOVERNANCE["default"], **metadata}
            for event_type, metadata in PAYMENT_EVENT_GOVERNANCE.items()
            if event_type != "default"
        },
    }


def get_payment_event_catalog() -> list[dict]:
    default_meta = dict(PAYMENT_EVENT_GOVERNANCE["default"])
    enriched = []
    for item in PAYMENT_EVENT_CATALOG:
        event_type = item["event_type"]
        governance = {**default_meta, **PAYMENT_EVENT_GOVERNANCE.get(event_type, {})}
        enriched.append({**dict(item), **governance})
    return enriched


def get_payment_event_runtime() -> dict:
    return {
        "aggregate_type": "payment",
        "transport_today": [
            "domain action / callback / worker",
            "payments.payment_intents.services or callback_service",
            "payments.payment_intents.event_service.publish_payment_event_after_commit",
            "payments.payment_intents.models.PaymentDomainEventOutbox",
            "management command / worker payments_publish_outbox -> publish_payment_outbox_event",
            "common.domain_events.publish_domain_event",
            "local listeners registrados con @subscribe",
            "dispatcher opcional common.gcp.pubsub_dispatcher",
        ],
        "ui_signal_path": [
            "payments domain event",
            "payments.payment_intents.event_handlers",
            "payments.payment_intents.realtime_services",
            "realtime.consumers.models.RealtimeSignal",
            "polling / SSE / futuros gateways WebSocket",
        ],
        "current_dispatch_mode": "payment_outbox_plus_optional_pubsub_plus_realtime_signals",
        "prepared_for": [
            "Pub/Sub dispatchers",
            "Cloud Run workers",
            "Cloud Tasks consumers",
            "API Gateway frontends",
        ],
    }


def build_payment_core_payload(payment_intent) -> dict:
    return {
        "payment_intent_id": _stringify_id(payment_intent.pk),
        "owner_id": _stringify_id(payment_intent.owner_id),
        "payment_type": payment_intent.payment_type,
        "rail": payment_intent.rail,
        "status": payment_intent.status,
        "provider": payment_intent.provider,
        "amount": str(payment_intent.amount),
        "currency": payment_intent.currency,
        "internal_reference": payment_intent.internal_reference,
        "external_reference": payment_intent.external_reference,
        "invoice_reference": payment_intent.invoice_reference,
        "provider_intent_id": payment_intent.provider_intent_id,
        "provider_reference": payment_intent.provider_reference,
        "provider_cus": payment_intent.provider_cus,
        "failure_code": payment_intent.failure_code,
        "failure_message": payment_intent.failure_message,
        "beneficiary_name": payment_intent.beneficiary_name,
        "beneficiary_document": payment_intent.beneficiary_document,
        "beneficiary_account_ref": payment_intent.beneficiary_account_ref,
        "pricing_snapshot": payment_intent.pricing_snapshot or {},
        "fee_breakdown": payment_intent.fee_breakdown or {},
        "tax_breakdown": payment_intent.tax_breakdown or {},
    }


def build_payment_intent_payload(payment_intent, *, change: str, extra: dict | None = None) -> dict:
    payload = {
        **build_payment_core_payload(payment_intent),
        "change": change,
    }
    if extra:
        payload.update(extra)
    return payload


def build_payment_usage_transition(*, before_counted: bool, after_counted: bool, amount) -> dict:
    return {
        "before_counted": bool(before_counted),
        "after_counted": bool(after_counted),
        "amount": str(amount),
    }


def build_payment_fee_payload(*, payment_intent, pricing_snapshot: dict) -> dict:
    return {
        "payment_intent_id": str(payment_intent.pk),
        "owner_id": str(payment_intent.owner_id),
        "provider": payment_intent.provider,
        "rail": payment_intent.rail,
        "payment_type": payment_intent.payment_type,
        "amount": str(payment_intent.amount),
        "currency": payment_intent.currency,
        "pricing_snapshot": pricing_snapshot or {},
    }
