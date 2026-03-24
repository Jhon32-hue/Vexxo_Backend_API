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
    Bounded contexts principales de Mindwallet.
    Sirven para clasificar y enrutar eventos entre módulos.
    """
    ACCOUNTS = "accounts"
    TRANSACTIONS = "transactions"
    ALERTS = "alerts"
    BUDGETS = "budgets"
    GOALS = "goals"
    CONTACTS = "contacts"
    DEBTS = "debts"
    REPORTS = "reports"
    FX = "fx"
    WEALTHFLOW = "wealthflow"
    INGEST = "ingest"
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
    Catálogo de eventos “oficiales” de Mindwallet.
    Aquí se documenta y versionan los eventos de dominio.
    """

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

    # --- TRANSACTIONS ---
    TRANSACTION_CREATED = "transactions.created.v1"
    TRANSACTION_UPDATED = "transactions.updated.v1"
    TRANSACTION_DELETED = "transactions.deleted.v1"
    TRANSACTION_IMPORTED = "transactions.imported.v1"

    # --- ALERTS ---
    ALERT_CREATED = "alerts.created.v1"
    #Recientemente agregado
    ALERT_AI_ENRICHED = "alerts.ai.enriched.v1"
    INSIGHT_GENERATED = "insight.generated.v1"
    ML_ANOMALY_DETECTED = "ml.anomaly.detected.v1"
    # --- DEBTS ---
    # DEBT_CREATED = "debts.created.v1"
    # DEBT_UPDATED = "debts.updated.v1" 
    # DEBT_DELETED = "debts.deleted.v1"
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
    EventNames.TRANSACTION_CREATED: "Transacción creada",
    EventNames.TRANSACTION_UPDATED: "Transacción actualizada",
    EventNames.TRANSACTION_DELETED: "Transacción eliminada",
    EventNames.TRANSACTION_IMPORTED: "Transacción importada desde proveedor externo",
    EventNames.ALERT_CREATED: "Alerta creada",
    #Recientemente agregado
    EventNames.ALERT_AI_ENRICHED: "Alerta enriquecida con IA",
    EventNames.INSIGHT_GENERATED: "Insight financiero generado",
    EventNames.ML_ANOMALY_DETECTED: "Anomalía detectada por ML",
    
}


# ========= MODELO DE EVENTO DE DOMINIO =========


@dataclass
class MindwalletDomainEvent:
    """
    Evento de dominio de Mindwallet.

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

EventHandler = Callable[[MindwalletDomainEvent], None]
EventDispatcher = Callable[[MindwalletDomainEvent], None]
EventMiddleware = Callable[[MindwalletDomainEvent], Optional[MindwalletDomainEvent]]


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


class DomainEventBus:
    """
    Bus de eventos en memoria para Mindwallet.

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

    def _apply_middlewares(self, event: MindwalletDomainEvent) -> Optional[MindwalletDomainEvent]:
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

    def _resolve_listeners(self, event: MindwalletDomainEvent) -> List[ListenerConfig]:
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

    def publish(self, event: MindwalletDomainEvent) -> None:
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

        # 1) Listeners locales
        for cfg in listeners:
            try:
                if cfg.run_async:
                    # Listener en thread aparte (fire-and-forget)
                    threading.Thread(
                        target=cfg.handler,
                        args=(event,),
                        name=f"event-listener-{cfg.name}",
                        daemon=True,
                    ).start()
                else:
                    cfg.handler(event)
            except Exception:
                logger.exception(
                    "[events] Error en listener '%s' para evento '%s'",
                    cfg.name,
                    event.type,
                )

        # 2) Dispatchers externos
        with self._lock:
            dispatchers = list(self._dispatchers)

        for dispatcher in dispatchers:
            try:
                dispatcher(event)
            except Exception:
                logger.exception(
                    "[events] Error en dispatcher externo para evento '%s'",
                    event.type,
                )


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
) -> MindwalletDomainEvent:
    """
    Helper único para publicar eventos de Mindwallet.

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

    event = MindwalletDomainEvent(
        type=event_type,
        context=context,
        payload=payload,
        metadata=_metadata,
        priority=priority,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    event_bus.publish(event)
    return event


def subscribe(
    event_type: str,
    *,
    name: Optional[str] = None,
    run_async: bool = False,
    contexts: Optional[List[EventContext]] = None,
    priority: EventPriority = EventPriority.NORMAL,
):
    """
    Decorador para listeners.

    Ejemplos:

        # Listener simple
        @subscribe(EventNames.ACCOUNT_BALANCE_UPDATED)
        def handle_balance_updated(event: MindwalletDomainEvent):
            ...

        # Listener solo para eventos de accounts.* en background y alta prioridad
        @subscribe("accounts.*", run_async=True, priority=EventPriority.HIGH)
        def handle_any_account_event(event: MindwalletDomainEvent):
            ...

        # Listener que solo escucha eventos de TRANSACTIONS dentro del contexto TRANSACTIONS
        @subscribe(EventNames.TRANSACTION_CREATED, contexts=[EventContext.TRANSACTIONS])
        def handle_tx_created(event: MindwalletDomainEvent):
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
        )
        return fn

    return wrapper
