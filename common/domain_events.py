# common/domain_events.py
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ========= CONTEXTOS Y NOMBRES DE EVENTO =========


class EventContext(str, Enum):
    """
    Bounded contexts principales de Vexxo_app.
    Sirven para clasificar y enrutar eventos entre módulos.
    """
    IDENTITY = "identity"
    ACCOUNTS = "accounts"
    TRANSACTIONS = "transactions"
    ALERTS = "alerts"
    PAYMENTS = "payments"
    BUDGETS = "budgets"
    GOALS = "goals"
    CONTACTS = "contacts"
    DEBTS = "debts"
    REPORTS = "reports"
    FX = "fx"
    WEALTHFLOW = "wealthflow"
    INGEST = "ingest"
    DOCUMENTS = "documents"
    SYSTEM = "system"


class EventPriority(IntEnum):
    """
    Prioridad relativa del evento para el orden de los listeners.
    No afecta el envío a Kafka/colas, solo el orden en memoria.
    """
    LOW = 10
    NORMAL = 20
    HIGH = 30
    CRITICAL = 40


class EventNames:
    """
    Catálogo de eventos “oficiales” de Vexxo_app.
    Aquí se documenta y versionan los eventos de dominio.
    """

    # --- IDENTITY / USERS ---
    USER_REGISTERED = "users.registered.v1"
    USER_PROFILE_UPDATED = "users.profile.updated.v1"
    USER_PLAN_CHANGED = "users.plan.changed.v1"
    USER_CURRENCY_CHANGED = "users.currency.changed.v1"
    USER_ONBOARDING_COMPLETED = "users.onboarding.completed.v1"
    USER_VERIFIED = "users.verified.v1"
    USER_SUSPENDED = "users.suspended.v1"
    USER_ACTIVATED = "users.activated.v1"
    USER_SOCIAL_AUTH_PREPARED = "users.social_auth.prepared.v1"
    USER_SOCIAL_LINKED = "users.social_identity.linked.v1"
    USER_SOCIAL_UNLINKED = "users.social_identity.unlinked.v1"
    USER_DEVICE_REGISTERED = "users.device.registered.v1"
    USER_DEVICE_TRUSTED = "users.device.trusted.v1"
    USER_DEVICE_REVOKED = "users.device.revoked.v1"
    USER_SESSION_STARTED = "users.session.started.v1"
    USER_SESSION_REVOKED = "users.session.revoked.v1"
    USER_CONSENT_GRANTED = "users.consent.granted.v1"
    USER_CONSENT_REVOKED = "users.consent.revoked.v1"
    USER_PERMISSION_GRANTED = "users.permission.granted.v1"
    USER_PERMISSION_DENIED = "users.permission.denied.v1"
    USER_PERMISSION_REVOKED = "users.permission.revoked.v1"
    GROWTH_UPGRADE_TRIGGERED = "growth.upgrade_triggered.v1"

    # --- ACCOUNTS ---
    ACCOUNT_BALANCE_UPDATED = "accounts.balance.updated.v1"
    ACCOUNT_CREATED = "accounts.created.v1"
    ACCOUNT_UPDATED = "accounts.updated.v1"
    ACCOUNT_CLOSED = "accounts.closed.v1"
    ACCOUNT_PRIMARY_CHANGED = "accounts.primary.changed.v1"
    ACCOUNT_FROZEN = "accounts.frozen.v1"
    ACCOUNT_UNFROZEN = "accounts.unfrozen.v1"
    ACCOUNT_ARCHIVED = "accounts.archived.v1"
    ACCOUNT_UNARCHIVED = "accounts.unarchived.v1"
    ACCOUNT_RECALCULATED = "accounts.recalculated.v1"
    ACCOUNT_SNAPSHOT_CREATED = "accounts.balance.snapshot.created.v1"
    BUDGET_CREATED = "budgets.created.v1"
    BUDGET_UPDATED = "budgets.updated.v1"
    BUDGET_DELETED = "budgets.deleted.v1"
    ACCOUNT_DRIFT_DETECTED = "accounts.balance.drift.detected.v1"
    ACCOUNT_EXTERNAL_LINKED = "accounts.external.linked.v1"
    ACCOUNT_EXTERNAL_UNLINKED = "accounts.external.unlinked.v1"
    ACCOUNT_SYNC_SCHEDULED = "accounts.sync.scheduled.v1"
    ACCOUNT_SYNC_STATUS_CHANGED = "accounts.sync.status.changed.v1"
    ACCOUNT_SYNC_STARTED = "accounts.sync.started.v1"
    ACCOUNT_SYNC_SUCCEEDED = "accounts.sync.succeeded.v1"
    ACCOUNT_SYNC_FAILED = "accounts.sync.failed.v1"
    ACCOUNT_MEMBERSHIP_CREATED = "accounts.membership.created.v1"
    ACCOUNT_MEMBERSHIP_INVITED = "accounts.membership.invited.v1"
    ACCOUNT_MEMBERSHIP_UPDATED = "accounts.membership.updated.v1"
    ACCOUNT_MEMBERSHIP_ACCEPTED = "accounts.membership.accepted.v1"
    ACCOUNT_MEMBERSHIP_REVOKED = "accounts.membership.revoked.v1"

    # --- PAYMENTS ---
    PAYMENT_ORDER_REQUESTED = "payments.order.requested.v1"
    PAYMENT_INTENT_CREATED = "payments.intent.created.v1"
    PAYMENT_INTENT_DISPATCHED = "payments.intent.dispatched.v1"
    PAYMENT_INTENT_REQUIRES_ACTION = "payments.intent.requires_action.v1"
    PAYMENT_INTENT_PROCESSING = "payments.intent.processing.v1"
    PAYMENT_INTENT_SUCCEEDED = "payments.intent.succeeded.v1"
    PAYMENT_INTENT_FAILED = "payments.intent.failed.v1"
    PAYMENT_INTENT_CANCELLED = "payments.intent.cancelled.v1"
    PAYMENT_INTENT_SETTLED = "payments.intent.settled.v1"
    PAYMENT_INTENT_REVERSED = "payments.intent.reversed.v1"
    PAYMENT_INTENT_DISPUTED = "payments.intent.disputed.v1"
    PAYMENT_FEE_CALCULATED = "payments.fee.calculated.v1"
    PAYMENT_PROVIDER_REFERENCE_RECORDED = "payments.provider.reference.recorded.v1"
    PAYMENT_CALLBACK_RECEIVED = "payments.callback.received.v1"
    PAYMENT_SETTLEMENT_RECORDED = "payments.settlement.recorded.v1"
    PAYMENT_RECURRING_TEMPLATE_CREATED = "payments.recurring.template.created.v1"
    PAYMENT_RECURRING_TEMPLATE_UPDATED = "payments.recurring.template.updated.v1"
    PAYMENT_RECURRING_TEMPLATE_DELETED = "payments.recurring.template.deleted.v1"
    PAYMENT_RECURRING_TEMPLATE_ACTIVATED = "payments.recurring.template.activated.v1"
    PAYMENT_RECURRING_TEMPLATE_DEACTIVATED = "payments.recurring.template.deactivated.v1"
    PAYMENT_RECURRING_RUN_REQUESTED = "payments.recurring.run.requested.v1"
    PAYMENT_PAYOUT_REQUESTED = "payments.payout.requested.v1"
    PAYMENT_PAYOUT_SUCCEEDED = "payments.payout.succeeded.v1"
    PAYMENT_PAYOUT_FAILED = "payments.payout.failed.v1"

    # --- TRANSACTIONS ---
    TRANSACTION_CREATED = "transactions.created.v1"
    TRANSACTION_UPDATED = "transactions.updated.v1"
    TRANSACTION_FINANCIAL_UPDATED = "transactions.financial.updated.v1"
    TRANSACTION_DELETED = "transactions.deleted.v1"
    TRANSACTION_IMPORTED = "transactions.imported.v1"
    TRANSACTION_INTAKE_BATCH_RECEIVED = "transactions.intake.batch.received.v1"
    TRANSACTION_INTAKE_BATCH_APPLIED = "transactions.intake.batch.applied.v1"
    TRANSACTION_INTAKE_BATCH_FAILED = "transactions.intake.batch.failed.v1"
    TRANSACTION_INTAKE_ROW_DUPLICATE_DETECTED = "transactions.intake.row.duplicate_detected.v1"
    TRANSACTION_RECONCILED = "transactions.reconciled.v1"
    TRANSACTION_CORRECTED = "transactions.corrected.v1"
    TRANSACTION_REVERSED = "transactions.reversed.v1"
    TRANSACTION_RECONCILIATION_ISSUE_RESOLVED = "transactions.reconciliation.issue.resolved.v1"
    TRANSACTION_CONFIRMED = "transactions.confirmed.v1"
    TRANSACTION_ACCOUNT_REASSIGNED = "transactions.account.reassigned.v1"
    TRANSACTION_REIMBURSEMENT_RECORDED = "transactions.reimbursement.recorded.v1"
    TRANSACTION_PARTICIPANT_CREATED = "transactions.participant.created.v1"
    TRANSACTION_PARTICIPANT_UPDATED = "transactions.participant.updated.v1"
    TRANSACTION_PARTICIPANT_DELETED = "transactions.participant.deleted.v1"
    TRANSACTION_PARTICIPANT_SETTLED = "transactions.participant.settled.v1"

    # --- ALERTS ---
    ALERT_CREATED = "alerts.created.v1"
    #Recientemente agregado
    ALERT_AI_ENRICHED = "alerts.ai.enriched.v1"
    INSIGHT_GENERATED = "insight.generated.v1"
    ML_ANOMALY_DETECTED = "ml.anomaly.detected.v1"
    # --- DEBTS ---
    DEBT_CREATED = "debts.created.v1"
    DEBT_UPDATED = "debts.updated.v1"
    DEBT_DELETED = "debts.deleted.v1"
    DEBT_INSTALLMENTS_GENERATED = "debts.installments.generated.v1"
    DEBT_INSTALLMENT_UPDATED = "debts.installment.updated.v1"
    DEBT_PAYMENT_APPLIED = "debts.payment.applied.v1"
    DEBT_STATUS_CHANGED = "debts.status.changed.v1"
    DEBT_OVERDUE_REFRESHED = "debts.overdue.refreshed.v1"

    # --- GOALS ---
    GOAL_CREATED = "goals.created.v1"
    GOAL_UPDATED = "goals.updated.v1"
    GOAL_STATUS_CHANGED = "goals.status.changed.v1"
    GOAL_CONTRIBUTION_RECORDED = "goals.contribution.recorded.v1"
    GOAL_CONTRIBUTION_REVERSED = "goals.contribution.reversed.v1"
    GOAL_PROGRESS_UPDATED = "goals.progress.updated.v1"
    # --- TRANSACTIONS ---
    # TRANSACTION_TAGGED = "transactions.tagged.v1"
    # TRANSACTION_UNTAGGED = "transactions.untagged.v1"
    # TRANSACTION_CATEGORIZED = "transactions.categorized.v1"
    # TRANSACTION_UNCATEGORIZED = "transactions.uncategorized.v1"
    # TRANSACTION_FLAGGED = "transactions.flagged.v1"
    # TRANSACTION_UNFLAGGED = "transactions.unflagged.v1"
    # TRANSACTION_SPLIT = "transactions.split.v1"
    # TRANSACTION_UNSPLIT = "transactions.unsplit.v1"
    # TRANSACTION_MATCHED = "transactions.matched.v1"
    # TRANSACTION_UNMATCHED = "transactions.unmatched.v1"
    # TRANSACTION_RECONCILED = "transactions.reconciled.v1"
    # TRANSACTION_UNRECONCILED = "transactions.unreconciled.v1"
    # TRANSACTION_NOTE_UPDATED = "transactions.note.updated.v1"
    # TRANSACTION_ATTACHMENT_ADDED = "transactions.attachment.added.v1"
    # TRANSACTION_ATTACHMENT_REMOVED = "transactions.attachment.removed.v1"
    # --- REPORTS ---
    # REPORT_GENERATED = "reports.generated.v1"
    # REPORT_SCHEDULED = "reports.scheduled.v1"
    # REPORT_DELIVERED = "reports.delivered.v1"
    # REPORT_FAILED = "reports.failed.v1"
    # --- OTROS ---
    # (Más adelante: budgets, goals, fx, wealthflow, etc.)
    # GOAL_PROGRESS_UPDATED = "goals.progress.updated.v1"
    # BUDGET_BREACHED = "budgets.breached.v1"
    # ...


KNOWN_EVENT_TYPES: Dict[str, str] = {
    EventNames.TRANSACTION_FINANCIAL_UPDATED: "Actualizacion financiera material de transaccion",
    EventNames.USER_REGISTERED: "Usuario registrado",
    EventNames.USER_PROFILE_UPDATED: "Perfil de usuario actualizado",
    EventNames.USER_PLAN_CHANGED: "Plan de usuario actualizado",
    EventNames.USER_CURRENCY_CHANGED: "Moneda base de usuario actualizada",
    EventNames.USER_ONBOARDING_COMPLETED: "Onboarding de usuario completado",
    EventNames.USER_VERIFIED: "Usuario verificado",
    EventNames.USER_SUSPENDED: "Usuario suspendido",
    EventNames.USER_ACTIVATED: "Usuario activado",
    EventNames.USER_SOCIAL_AUTH_PREPARED: "Proveedor social consultado o preparado",
    EventNames.USER_SOCIAL_LINKED: "Identidad social vinculada a usuario",
    EventNames.USER_SOCIAL_UNLINKED: "Identidad social desvinculada de usuario",
    EventNames.USER_DEVICE_REGISTERED: "Dispositivo de usuario registrado",
    EventNames.USER_DEVICE_TRUSTED: "Dispositivo de usuario marcado como confiable",
    EventNames.USER_DEVICE_REVOKED: "Dispositivo de usuario revocado",
    EventNames.USER_SESSION_STARTED: "Sesion de usuario iniciada",
    EventNames.USER_SESSION_REVOKED: "Sesion de usuario revocada",
    EventNames.USER_CONSENT_GRANTED: "Consentimiento de usuario otorgado",
    EventNames.USER_CONSENT_REVOKED: "Consentimiento de usuario revocado",
    EventNames.USER_PERMISSION_GRANTED: "Grant de permiso de usuario otorgado",
    EventNames.USER_PERMISSION_DENIED: "Grant de permiso de usuario denegado explicitamente",
    EventNames.USER_PERMISSION_REVOKED: "Grant de permiso de usuario revocado",
    EventNames.GROWTH_UPGRADE_TRIGGERED: "Trigger de upgrade por limite de plan o friccion de valor",
    # type: descripción corta
    EventNames.ACCOUNT_BALANCE_UPDATED: "Balance de una cuenta recalculado",
    EventNames.ACCOUNT_CREATED: "Cuenta creada",
    EventNames.ACCOUNT_UPDATED: "Cuenta actualizada",
    EventNames.ACCOUNT_CLOSED: "Cuenta cerrada",
    EventNames.ACCOUNT_PRIMARY_CHANGED: "Cuenta principal actualizada",
    EventNames.ACCOUNT_FROZEN: "Cuenta congelada",
    EventNames.ACCOUNT_UNFROZEN: "Cuenta descongelada",
    EventNames.ACCOUNT_ARCHIVED: "Cuenta archivada",
    EventNames.ACCOUNT_UNARCHIVED: "Cuenta desarchivada",
    EventNames.ACCOUNT_RECALCULATED: "Balance de cuenta recalculado manualmente",
    EventNames.ACCOUNT_SNAPSHOT_CREATED: "Snapshot de balance de cuenta creado",
    EventNames.BUDGET_CREATED: "Presupuesto creado",
    EventNames.BUDGET_UPDATED: "Presupuesto actualizado",
    EventNames.BUDGET_DELETED: "Presupuesto eliminado",
    EventNames.ACCOUNT_DRIFT_DETECTED: "Drift detectado entre cache y ledger de cuenta",
    EventNames.ACCOUNT_EXTERNAL_LINKED: "Cuenta vinculada a proveedor externo",
    EventNames.ACCOUNT_EXTERNAL_UNLINKED: "Cuenta desvinculada de proveedor externo",
    EventNames.ACCOUNT_SYNC_SCHEDULED: "Sincronizacion de cuenta programada",
    EventNames.ACCOUNT_SYNC_STATUS_CHANGED: "Estado de sincronizacion de cuenta actualizado",
    EventNames.ACCOUNT_SYNC_STARTED: "Sincronizacion de cuenta iniciada",
    EventNames.ACCOUNT_SYNC_SUCCEEDED: "Sincronizacion de cuenta completada",
    EventNames.ACCOUNT_SYNC_FAILED: "Sincronizacion de cuenta fallida",
    EventNames.ACCOUNT_MEMBERSHIP_CREATED: "Membresia de cuenta creada",
    EventNames.ACCOUNT_MEMBERSHIP_INVITED: "Invitacion a membresia de cuenta emitida",
    EventNames.ACCOUNT_MEMBERSHIP_UPDATED: "Membresia de cuenta actualizada",
    EventNames.ACCOUNT_MEMBERSHIP_ACCEPTED: "Membresia de cuenta aceptada",
    EventNames.ACCOUNT_MEMBERSHIP_REVOKED: "Membresia de cuenta revocada",
    EventNames.PAYMENT_ORDER_REQUESTED: "Orden de pago solicitada por el usuario",
    EventNames.PAYMENT_INTENT_CREATED: "Intent de pago creado",
    EventNames.PAYMENT_INTENT_DISPATCHED: "Intent de pago despachado al proveedor",
    EventNames.PAYMENT_INTENT_REQUIRES_ACTION: "Intent de pago requiere accion adicional",
    EventNames.PAYMENT_INTENT_PROCESSING: "Intent de pago en procesamiento",
    EventNames.PAYMENT_INTENT_SUCCEEDED: "Intent de pago ejecutado correctamente",
    EventNames.PAYMENT_INTENT_FAILED: "Intent de pago fallido",
    EventNames.PAYMENT_INTENT_CANCELLED: "Intent de pago cancelado",
    EventNames.PAYMENT_INTENT_SETTLED: "Intent de pago liquidado",
    EventNames.PAYMENT_INTENT_REVERSED: "Intent de pago revertido",
    EventNames.PAYMENT_INTENT_DISPUTED: "Intent de pago en disputa",
    EventNames.PAYMENT_FEE_CALCULATED: "Fee de pago calculado",
    EventNames.PAYMENT_PROVIDER_REFERENCE_RECORDED: "Referencia del proveedor registrada",
    EventNames.PAYMENT_CALLBACK_RECEIVED: "Callback de proveedor recibido",
    EventNames.PAYMENT_SETTLEMENT_RECORDED: "Settlement de pago registrado",
    EventNames.PAYMENT_RECURRING_TEMPLATE_CREATED: "Template recurrente de pago creado",
    EventNames.PAYMENT_RECURRING_TEMPLATE_UPDATED: "Template recurrente de pago actualizado",
    EventNames.PAYMENT_RECURRING_TEMPLATE_DELETED: "Template recurrente de pago eliminado",
    EventNames.PAYMENT_RECURRING_TEMPLATE_ACTIVATED: "Template recurrente de pago activado",
    EventNames.PAYMENT_RECURRING_TEMPLATE_DEACTIVATED: "Template recurrente de pago desactivado",
    EventNames.PAYMENT_RECURRING_RUN_REQUESTED: "Corrida recurrente de pago solicitada",
    EventNames.PAYMENT_PAYOUT_REQUESTED: "Dispersion solicitada",
    EventNames.PAYMENT_PAYOUT_SUCCEEDED: "Dispersion completada",
    EventNames.PAYMENT_PAYOUT_FAILED: "Dispersion fallida",
    EventNames.TRANSACTION_CREATED: "Transacción creada",
    EventNames.TRANSACTION_UPDATED: "Transacción actualizada",
    EventNames.TRANSACTION_DELETED: "Transacción eliminada",
    EventNames.TRANSACTION_IMPORTED: "Transacción importada desde proveedor externo",
    EventNames.TRANSACTION_INTAKE_BATCH_RECEIVED: "Batch de intake de transacciones recibido",
    EventNames.TRANSACTION_INTAKE_BATCH_APPLIED: "Batch de intake de transacciones aplicado",
    EventNames.TRANSACTION_INTAKE_BATCH_FAILED: "Batch de intake de transacciones fallido",
    EventNames.TRANSACTION_INTAKE_ROW_DUPLICATE_DETECTED: "Fila duplicada detectada durante intake",
    EventNames.TRANSACTION_RECONCILED: "Transaccion reconciliada con fuente externa",
    EventNames.TRANSACTION_CORRECTED: "Transaccion marcada para correccion formal",
    EventNames.TRANSACTION_REVERSED: "Transaccion revertida o marcada para reverso",
    EventNames.TRANSACTION_RECONCILIATION_ISSUE_RESOLVED: "Issue de reconciliacion de transaccion resuelto formalmente",
    EventNames.TRANSACTION_CONFIRMED: "Transaccion confirmada",
    EventNames.TRANSACTION_ACCOUNT_REASSIGNED: "Cuenta de transaccion reasignada",
    EventNames.TRANSACTION_REIMBURSEMENT_RECORDED: "Reembolso registrado sobre transaccion",
    EventNames.TRANSACTION_PARTICIPANT_CREATED: "Participante de transaccion creado",
    EventNames.TRANSACTION_PARTICIPANT_UPDATED: "Participante de transaccion actualizado",
    EventNames.TRANSACTION_PARTICIPANT_DELETED: "Participante de transaccion eliminado",
    EventNames.TRANSACTION_PARTICIPANT_SETTLED: "Participante de transaccion liquidado",
    EventNames.ALERT_CREATED: "Alerta creada",
    EventNames.DEBT_CREATED: "Deuda creada",
    EventNames.DEBT_UPDATED: "Deuda actualizada",
    EventNames.DEBT_DELETED: "Deuda eliminada",
    EventNames.DEBT_INSTALLMENTS_GENERATED: "Cuotas de deuda generadas",
    EventNames.DEBT_INSTALLMENT_UPDATED: "Cuota de deuda actualizada",
    EventNames.DEBT_PAYMENT_APPLIED: "Pago aplicado a deuda",
    EventNames.DEBT_STATUS_CHANGED: "Estado de deuda actualizado",
    EventNames.DEBT_OVERDUE_REFRESHED: "Vencimientos de deuda recalculados",
    EventNames.GOAL_CREATED: "Meta creada",
    EventNames.GOAL_UPDATED: "Meta actualizada",
    EventNames.GOAL_STATUS_CHANGED: "Estado de meta actualizado",
    EventNames.GOAL_CONTRIBUTION_RECORDED: "Aporte a meta registrado",
    EventNames.GOAL_CONTRIBUTION_REVERSED: "Aporte a meta revertido",
    EventNames.GOAL_PROGRESS_UPDATED: "Progreso de meta actualizado",
    #Recientemente agregado
    EventNames.ALERT_AI_ENRICHED: "Alerta enriquecida con IA",
    EventNames.INSIGHT_GENERATED: "Insight financiero generado",
    EventNames.ML_ANOMALY_DETECTED: "Anomalía detectada por ML",

}


# ========= MODELO DE EVENTO DE DOMINIO =========


@dataclass
class VexxoAppDomainEvent:
    """
    Evento de dominio de Vexxo_app.

    type:
      - Nombre versionado del evento (ver EventNames).

    context:
      - Bounded context principal (EventContext).

    payload:
      - Datos de negocio del evento.

    metadata:
      - Contexto técnico:
        - source (módulo/archivo que lo emitió)
        - request_id / correlation_id / user_id, etc.

    priority:
      - Prioridad para el orden de ejecución de listeners locales.

    correlation_id / causation_id:
      - Para trazabilidad entre cadenas de eventos.
    """

    type: str
    context: EventContext
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "v1"

    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "context": self.context.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "payload": self.payload,
            "metadata": self.metadata,
            "priority": int(self.priority),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }


# ========= BUS EN MEMORIA (LOCAL) =========

EventHandler = Callable[[VexxoAppDomainEvent], None]
EventDispatcher = Callable[[VexxoAppDomainEvent], None]
EventMiddleware = Callable[[VexxoAppDomainEvent], Optional[VexxoAppDomainEvent]]


@dataclass
class ListenerConfig:
    """
    Configuración de un listener.

    - name: nombre lógico (para logs/observabilidad)
    - run_async: si True se ejecuta en un thread aparte
    - contexts: si se define, solo recibe eventos de esos contexts
    - priority: orden relativo entre listeners del mismo evento
    """
    handler: EventHandler
    name: str
    run_async: bool = False
    contexts: Optional[List[EventContext]] = None
    priority: EventPriority = EventPriority.NORMAL
    required: bool = False


class DomainEventBus:
    """
    Bus de eventos en memoria para Vexxo_app.

    - Registra listeners por tipo de evento (exacto) y por patrón ("accounts.*").
    - Ejecuta middlewares antes de despachar (pueden mutar o cancelar el evento).
    - Publica a listeners locales (sincrónico o en hilo aparte).
    - Dispara dispatchers externos (Kafka/colas/webhooks) si se registran.
    """

    def __init__(self) -> None:
        # listeners["accounts.balance.updated.v1"] = [ListenerConfig, ...]
        self._listeners: Dict[str, List[ListenerConfig]] = {}
        # pattern_listeners["accounts.*"] = [ListenerConfig, ...]
        self._pattern_listeners: Dict[str, List[ListenerConfig]] = {}
        self._dispatchers: List[EventDispatcher] = []
        self._middlewares: List[EventMiddleware] = []
        self._lock = threading.RLock()

    # ---- Suscripción local ----

    def register_listener(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        name: Optional[str] = None,
        run_async: bool = False,
        contexts: Optional[List[EventContext]] = None,
        priority: EventPriority = EventPriority.NORMAL,
        required: bool = False,
    ) -> None:
        """
        Registra un listener para un tipo de evento.

        Soporta:
        - event_type exacto: "accounts.balance.updated.v1"
        - patrón: "accounts.*" para escuchar todos los eventos de accounts
        """
        cfg = ListenerConfig(
            handler=handler,
            name=name or handler.__name__,
            run_async=run_async,
            contexts=contexts,
            priority=priority,
            required=required,
        )

        with self._lock:
            if event_type.endswith(".*"):
                logger.debug(
                    "Registrando listener pattern=%s handler=%s",
                    event_type,
                    cfg.name,
                )
                self._pattern_listeners.setdefault(event_type, []).append(cfg)
            else:
                if event_type not in KNOWN_EVENT_TYPES:
                    logger.warning(
                        "[events] Registrando listener para tipo NO registrado '%s'. "
                        "Considera agregarlo a KNOWN_EVENT_TYPES.",
                        event_type,
                    )
                logger.debug(
                    "Registrando listener %s para %s",
                    cfg.name,
                    event_type,
                )
                self._listeners.setdefault(event_type, []).append(cfg)

    # ---- Middleware global ----

    def register_middleware(self, middleware: EventMiddleware) -> None:
        """
        Middleware global que se ejecuta antes de despachar el evento.

        - Puede mutar el evento y devolverlo.
        - Puede devolver None para CANCELAR la publicación.
        """
        with self._lock:
            self._middlewares.append(middleware)

    # ---- Backends externos (Kafka, etc.) ----

    def register_dispatcher(self, dispatcher: EventDispatcher) -> None:
        """
        Dispatcher = función que envía el evento a un sistema externo
        (Kafka, SQS, Redis, webhooks, etc.).
        """
        with self._lock:
            self._dispatchers.append(dispatcher)

    # ---- Publicación ----

    def _apply_middlewares(self, event: VexxoAppDomainEvent) -> Optional[VexxoAppDomainEvent]:
        with self._lock:
            middlewares = list(self._middlewares)

        for mw in middlewares:
            try:
                modified = mw(event)
                if modified is None:
                    logger.debug(
                        "[events] Evento %s (%s) cancelado por middleware '%s'",
                        event.type,
                        event.id,
                        mw.__name__,
                    )
                    return None
                event = modified
            except Exception:
                logger.exception(
                    "[events] Error en middleware '%s' para evento '%s'",
                    mw.__name__,
                    event.type,
                )
        return event

    def _resolve_listeners(self, event: VexxoAppDomainEvent) -> List[ListenerConfig]:
        with self._lock:
            exact_listeners = list(self._listeners.get(event.type, []))
            pattern_items = list(self._pattern_listeners.items())

        # Listeners por patrón: "accounts.*" -> todos los eventos de accounts
        pattern_listeners: List[ListenerConfig] = []
        for pattern, cfgs in pattern_items:
            prefix = pattern[:-2]  # "accounts.*" -> "accounts."
            if event.type.startswith(prefix):
                pattern_listeners.extend(cfgs)

        all_listeners = exact_listeners + pattern_listeners

        # Filtrado por context
        filtered: List[ListenerConfig] = []
        for cfg in all_listeners:
            if cfg.contexts and event.context not in cfg.contexts:
                continue
            filtered.append(cfg)

        # Ordenados por prioridad (CRITICAL primero)
        filtered.sort(key=lambda c: int(c.priority), reverse=True)
        return filtered

    def publish(
        self,
        event: VexxoAppDomainEvent,
        *,
        include_local: bool = True,
        include_external: bool = True,
        raise_required_listener_errors: bool = False,
    ) -> None:
        """
        Publica el evento a:
        - Middlewares globales
        - Listeners locales (sincrónico / en hilo aparte)
        - Dispatchers externos
        """
        # 0) Middlewares
        event = self._apply_middlewares(event)
        if event is None:
            return

        if event.type not in KNOWN_EVENT_TYPES:
            logger.debug(
                "[events] Publicando evento de tipo NO registrado '%s'. "
                "Esto es válido, pero considera documentarlo.",
                event.type,
            )

        logger.debug(
            "[events] Publicando evento %s (%s) context=%s priority=%s",
            event.type,
            event.id,
            event.context.value,
            event.priority.name,
        )

        listeners = self._resolve_listeners(event)

        if include_local:
            required_listener_errors = []
            for cfg in listeners:
                try:
                    # `run_async` permanece en el registro por compatibilidad.
                    # La ejecucion ocurre en el caller actual, normalmente el
                    # publicador durable del outbox. Los callers directos ven
                    # el resultado en vez de perder trabajo en un thread.
                    cfg.handler(event)
                except Exception as exc:
                    logger.exception(
                        "[events] Error en listener '%s' para evento '%s'",
                        cfg.name,
                        event.type,
                    )
                    if (cfg.required or cfg.run_async) and raise_required_listener_errors:
                        required_listener_errors.append(exc)

            if required_listener_errors:
                raise required_listener_errors[0]

        if include_external:
            with self._lock:
                dispatchers = list(self._dispatchers)

            dispatcher_errors = []
            for dispatcher in dispatchers:
                try:
                    dispatcher(event)
                except Exception as exc:
                    dispatcher_errors.append(exc)
                    logger.exception(
                        "[events] Error en dispatcher externo para evento '%s'",
                        event.type,
                    )
            if dispatcher_errors:
                raise dispatcher_errors[0]


# Instancia global (tipo singleton)
event_bus = DomainEventBus()


# ========= HELPERS DE ALTO NIVEL =========


def publish_domain_event(
    event_type: str,
    context: EventContext,
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    *,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    include_local: bool = True,
    include_external: bool = True,
    raise_required_listener_errors: bool = False,
) -> VexxoAppDomainEvent:
    """
    Helper único para publicar eventos de Vexxo_app.

    Ejemplo:

        publish_domain_event(
            EventNames.ACCOUNT_BALANCE_UPDATED,
            context=EventContext.ACCOUNTS,
            payload={...},
            metadata={"source": "accounts.signals", "user_id": user.id},
            priority=EventPriority.HIGH,
        )
    """
    _metadata = metadata.copy() if metadata else {}

    # Si no hay correlation_id, lo generamos o reutilizamos si viene en metadata
    if correlation_id is None:
        correlation_id = _metadata.get("correlation_id") or str(uuid.uuid4())
    else:
        _metadata["correlation_id"] = correlation_id

    event = VexxoAppDomainEvent(
        type=event_type,
        context=context,
        payload=payload,
        metadata=_metadata,
        priority=priority,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    event_bus.publish(
        event,
        include_local=include_local,
        include_external=include_external,
        raise_required_listener_errors=raise_required_listener_errors,
    )
    return event


def subscribe(
    event_type: str,
    *,
    name: Optional[str] = None,
    run_async: bool = False,
    contexts: Optional[List[EventContext]] = None,
    priority: EventPriority = EventPriority.NORMAL,
    required: bool = False,
):
    """
    Decorador para listeners.

    Ejemplos:

        # Listener simple
        @subscribe(EventNames.ACCOUNT_BALANCE_UPDATED)
        def handle_balance_updated(event: VexxoAppDomainEvent):
            ...

        # Listener solo para eventos de accounts.* en background y alta prioridad
        @subscribe("accounts.*", run_async=True, priority=EventPriority.HIGH)
        def handle_any_account_event(event: VexxoAppDomainEvent):
            ...

        # Listener que solo escucha eventos de TRANSACTIONS dentro del contexto TRANSACTIONS
        @subscribe(EventNames.TRANSACTION_CREATED, contexts=[EventContext.TRANSACTIONS])
        def handle_tx_created(event: VexxoAppDomainEvent):
            ...
    """

    def wrapper(fn: EventHandler):
        event_bus.register_listener(
            event_type,
            fn,
            name=name,
            run_async=run_async,
            contexts=contexts,
            priority=priority,
            required=required,
        )
        return fn

    return wrapper
