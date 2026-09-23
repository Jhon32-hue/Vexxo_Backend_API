from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from common.domain_events import EventNames, VexxoAppDomainEvent
from notifications.deliveries.models import NotificationCategory, NotificationPriority

Payload = dict
TextBuilder = Callable[[Payload], str]


@dataclass(frozen=True)
class NotificationDefinition:
    key: str
    category: str
    priority: str
    title: str | TextBuilder
    message: str | TextBuilder
    action_path: str
    recipient_field: str = "owner_id"
    payload_fields: tuple[str, ...] = ()
    version: int = 1

    def render_title(self, payload: Payload) -> str:
        return self.title(payload) if callable(self.title) else self.title

    def render_message(self, payload: Payload) -> str:
        return self.message(payload) if callable(self.message) else self.message


def _money(payload: Payload) -> str:
    amount = str(payload.get("amount") or "").strip()
    currency = str(payload.get("currency") or "").strip().upper()
    return " ".join(value for value in (amount, currency) if value) or "el monto indicado"


def _transaction_kind(payload: Payload) -> str:
    return {
        "expense": "Gasto",
        "income": "Ingreso",
        "transfer": "Transferencia",
    }.get(str(payload.get("type") or "").lower(), "Movimiento")


def _transaction_created_title(payload: Payload) -> str:
    suffix = "registrado" if bool(payload.get("confirmed")) else "guardado para revision"
    return f"{_transaction_kind(payload)} {suffix}"


def _transaction_created_message(payload: Payload) -> str:
    description = str(payload.get("description") or "").strip()
    prefix = f"{description}: " if description else ""
    return f"{prefix}{_money(payload)} quedo registrado en Vexxo."


def _account_created_message(payload: Payload) -> str:
    return f"La cuenta {payload.get('name') or 'financiera'} ya esta disponible en tu espacio financiero."


def _payment_requires_action(payload: Payload) -> str:
    provider = str(payload.get("provider") or "el proveedor")
    return f"El pago por {_money(payload)} con {provider} requiere una accion adicional para continuar."


def _payment_failed(payload: Payload) -> str:
    provider = str(payload.get("provider") or "el proveedor")
    reason = str(payload.get("failure_message") or "").strip()
    suffix = f": {reason}" if reason else "."
    return f"El pago por {_money(payload)} con {provider} no pudo completarse{suffix}"


def _definition(
    key: str,
    category: str,
    title: str | TextBuilder,
    message: str | TextBuilder,
    action_path: str,
    *,
    priority: str = NotificationPriority.NORMAL,
    recipient_field: str = "owner_id",
    payload_fields: tuple[str, ...] = (),
) -> NotificationDefinition:
    return NotificationDefinition(
        key=key,
        category=category,
        priority=priority,
        title=title,
        message=message,
        action_path=action_path,
        recipient_field=recipient_field,
        payload_fields=payload_fields,
    )


NOTIFICATION_CATALOG: dict[str, NotificationDefinition] = {
    EventNames.USER_REGISTERED: _definition(
        "identity.welcome",
        NotificationCategory.LIFECYCLE,
        "Bienvenido a Vexxo",
        "Tu espacio financiero esta listo. Completa la configuracion inicial para personalizarlo.",
        "/onboarding/setup",
        recipient_field="user_id",
        payload_fields=("user_id",),
    ),
    EventNames.USER_ONBOARDING_COMPLETED: _definition(
        "identity.onboarding.completed",
        NotificationCategory.LIFECYCLE,
        "Configuracion completada",
        "Vexxo ya puede adaptar la experiencia a tus objetivos financieros.",
        "/dashboard",
        recipient_field="user_id",
        payload_fields=("user_id", "profile_version"),
    ),
    EventNames.USER_DEVICE_REGISTERED: _definition(
        "security.device.registered",
        NotificationCategory.SECURITY,
        "Nuevo dispositivo registrado",
        "Se registro un dispositivo para acceder a tu cuenta.",
        "/settings",
        priority=NotificationPriority.HIGH,
        recipient_field="user_id",
        payload_fields=("device_id",),
    ),
    EventNames.USER_DEVICE_REVOKED: _definition(
        "security.device.revoked",
        NotificationCategory.SECURITY,
        "Dispositivo revocado",
        "Un dispositivo dejo de tener acceso a tu cuenta.",
        "/settings",
        priority=NotificationPriority.HIGH,
        recipient_field="user_id",
        payload_fields=("device_id",),
    ),
    EventNames.ACCOUNT_CREATED: _definition(
        "finance.account.created",
        NotificationCategory.FINANCE,
        "Cuenta creada",
        _account_created_message,
        "/shared-accounts",
        payload_fields=("account_id", "name"),
    ),
    EventNames.ACCOUNT_PRIMARY_CHANGED: _definition(
        "finance.account.primary_changed",
        NotificationCategory.FINANCE,
        "Cuenta principal actualizada",
        lambda payload: f"La cuenta {payload.get('name') or 'financiera'} ahora es tu cuenta principal.",
        "/shared-accounts",
        priority=NotificationPriority.LOW,
        payload_fields=("account_id", "name"),
    ),
    EventNames.ACCOUNT_ARCHIVED: _definition(
        "finance.account.archived",
        NotificationCategory.FINANCE,
        "Cuenta archivada",
        lambda payload: f"La cuenta {payload.get('name') or 'financiera'} fue archivada.",
        "/shared-accounts",
        priority=NotificationPriority.LOW,
        payload_fields=("account_id", "name"),
    ),
    EventNames.ACCOUNT_MEMBERSHIP_INVITED: _definition(
        "collaboration.account.invited",
        NotificationCategory.COLLABORATION,
        "Te compartieron una cuenta",
        "Tienes una nueva invitacion para colaborar en una cuenta financiera.",
        "/collaboration/invitations",
        recipient_field="user_id",
        payload_fields=("account_id", "membership_id"),
    ),
    EventNames.ACCOUNT_MEMBERSHIP_ACCEPTED: _definition(
        "collaboration.account.accepted",
        NotificationCategory.COLLABORATION,
        "Invitacion aceptada",
        "Un colaborador acepto la invitacion a una de tus cuentas compartidas.",
        "/shared-accounts",
        payload_fields=("account_id", "membership_id"),
    ),
    EventNames.ACCOUNT_MEMBERSHIP_REVOKED: _definition(
        "collaboration.account.revoked",
        NotificationCategory.COLLABORATION,
        "Acceso revocado",
        "El acceso a una cuenta compartida fue revocado o finalizado.",
        "/shared-accounts",
        recipient_field="user_id",
        payload_fields=("account_id", "membership_id"),
    ),
    EventNames.ACCOUNT_SYNC_SUCCEEDED: _definition(
        "integration.account.sync_succeeded",
        NotificationCategory.INTEGRATION,
        "Sincronizacion completada",
        lambda payload: f"La cuenta {payload.get('name') or 'financiera'} se sincronizo correctamente.",
        "/integrations/open-banking",
        priority=NotificationPriority.LOW,
        payload_fields=("account_id", "name", "provider", "imported_count"),
    ),
    EventNames.ACCOUNT_SYNC_FAILED: _definition(
        "integration.account.sync_failed",
        NotificationCategory.INTEGRATION,
        "No pudimos actualizar una cuenta",
        "La conexion bancaria necesita una revision o un nuevo intento.",
        "/integrations/open-banking",
        priority=NotificationPriority.HIGH,
        payload_fields=("account_id", "provider"),
    ),
    EventNames.TRANSACTION_CREATED: _definition(
        "finance.transaction.recorded",
        NotificationCategory.FINANCE,
        _transaction_created_title,
        _transaction_created_message,
        "/transactions",
        payload_fields=("transaction_id", "type", "amount", "currency", "description", "confirmed"),
    ),
    EventNames.TRANSACTION_IMPORTED: _definition(
        "finance.transaction.imported",
        NotificationCategory.INTEGRATION,
        "Movimiento bancario importado",
        lambda payload: f"Vexxo importo {_money(payload)} para que puedas revisarlo.",
        "/transactions/imported-review",
        payload_fields=("transaction_id", "amount", "currency", "provider"),
    ),
    EventNames.TRANSACTION_CONFIRMED: _definition(
        "finance.transaction.confirmed",
        NotificationCategory.FINANCE,
        "Movimiento confirmado",
        lambda payload: f"El {_transaction_kind(payload).lower()} por {_money(payload)} ya hace parte de tu informacion confirmada.",
        "/transactions",
        payload_fields=("transaction_id", "type", "amount", "currency"),
    ),
    EventNames.TRANSACTION_REVERSED: _definition(
        "finance.transaction.reversed",
        NotificationCategory.FINANCE,
        "Movimiento revertido",
        "La correccion quedo registrada sin eliminar la trazabilidad original.",
        "/transactions",
        priority=NotificationPriority.HIGH,
        payload_fields=("transaction_id", "reversal_transaction_id"),
    ),
    EventNames.TRANSACTION_REIMBURSEMENT_RECORDED: _definition(
        "finance.transaction.reimbursed",
        NotificationCategory.FINANCE,
        "Reembolso registrado",
        "El reembolso quedo vinculado al movimiento original.",
        "/transactions",
        payload_fields=("transaction_id", "reimbursement_transaction_id"),
    ),
    EventNames.TRANSACTION_ACCOUNT_REASSIGNED: _definition(
        "finance.transaction.account_reassigned",
        NotificationCategory.FINANCE,
        "Movimiento reasignado",
        "El movimiento quedo asociado a la cuenta seleccionada.",
        "/transactions",
        payload_fields=("transaction_id", "account_id"),
    ),
    EventNames.BUDGET_CREATED: _definition(
        "finance.budget.created",
        NotificationCategory.FINANCE,
        "Presupuesto creado",
        "Tu limite de gasto ya esta activo para el periodo seleccionado.",
        "/budgets",
        priority=NotificationPriority.LOW,
        payload_fields=("budget_id", "scope_type", "month", "amount"),
    ),
    EventNames.BUDGET_UPDATED: _definition(
        "finance.budget.updated",
        NotificationCategory.FINANCE,
        "Presupuesto actualizado",
        "Los cambios del presupuesto quedaron guardados.",
        "/budgets",
        priority=NotificationPriority.LOW,
        payload_fields=("budget_id", "scope_type", "month", "amount"),
    ),
    EventNames.BUDGET_DELETED: _definition(
        "finance.budget.deleted",
        NotificationCategory.FINANCE,
        "Presupuesto eliminado",
        "El presupuesto dejo de participar en el seguimiento del periodo.",
        "/budgets",
        priority=NotificationPriority.LOW,
        payload_fields=("budget_id", "scope_type", "month"),
    ),
    EventNames.SHARED_EXPENSE_CREATED: _definition(
        "collaboration.shared_expense.created",
        NotificationCategory.COLLABORATION,
        "Gasto compartido creado",
        "El reparto quedo guardado y las invitaciones fueron generadas.",
        "/shared-expenses",
        payload_fields=("shared_expense_id", "transaction_id", "status", "version"),
    ),
    EventNames.SHARED_EXPENSE_SHARE_INVITED: _definition(
        "collaboration.shared_expense.invited",
        NotificationCategory.COLLABORATION,
        "Te invitaron a dividir un gasto",
        "Tienes una parte pendiente por revisar y aceptar.",
        "/shared-expenses",
        priority=NotificationPriority.HIGH,
        recipient_field="participant_user_id",
        payload_fields=("shared_expense_id", "share_id", "amount", "currency"),
    ),
    EventNames.SHARED_EXPENSE_SHARE_ACCEPTED: _definition(
        "collaboration.shared_expense.accepted",
        NotificationCategory.COLLABORATION,
        "Una parte fue aceptada",
        "Un participante confirmo su parte del gasto compartido.",
        "/shared-expenses",
        payload_fields=("shared_expense_id", "share_id", "status", "version"),
    ),
    EventNames.SHARED_EXPENSE_REVISED: _definition(
        "collaboration.shared_expense.revised",
        NotificationCategory.COLLABORATION,
        "Gasto compartido actualizado",
        "El reparto cambio y conserva el historial de la version anterior.",
        "/shared-expenses",
        payload_fields=("shared_expense_id", "status", "version"),
    ),
    EventNames.SHARED_EXPENSE_SETTLEMENT_RECORDED: _definition(
        "collaboration.shared_expense.settled",
        NotificationCategory.COLLABORATION,
        "Pago compartido registrado",
        "Una liquidacion quedo vinculada a un movimiento real.",
        "/shared-expenses",
        payload_fields=("shared_expense_id", "share_id", "settlement_id", "amount", "status", "version"),
    ),
    EventNames.SHARED_EXPENSE_DISPUTED: _definition(
        "collaboration.shared_expense.disputed",
        NotificationCategory.COLLABORATION,
        "Gasto compartido en revision",
        "Una parte fue disputada y requiere revision de los participantes.",
        "/shared-expenses",
        priority=NotificationPriority.HIGH,
        payload_fields=("shared_expense_id", "share_id", "status", "version"),
    ),
    EventNames.SHARED_EXPENSE_CANCELED: _definition(
        "collaboration.shared_expense.canceled",
        NotificationCategory.COLLABORATION,
        "Gasto compartido cancelado",
        "El reparto fue cancelado y conserva su trazabilidad.",
        "/shared-expenses",
        payload_fields=("shared_expense_id", "status", "version"),
    ),
    EventNames.PAYMENT_INTENT_REQUIRES_ACTION: _definition(
        "finance.payment.requires_action",
        NotificationCategory.FINANCE,
        "Tu pago requiere accion",
        _payment_requires_action,
        "/activity",
        priority=NotificationPriority.HIGH,
        payload_fields=("payment_intent_id", "amount", "currency", "provider"),
    ),
    EventNames.PAYMENT_INTENT_SUCCEEDED: _definition(
        "finance.payment.succeeded",
        NotificationCategory.FINANCE,
        "Pago completado",
        lambda payload: f"El pago por {_money(payload)} fue confirmado.",
        "/activity",
        payload_fields=("payment_intent_id", "amount", "currency", "provider"),
    ),
    EventNames.PAYMENT_INTENT_FAILED: _definition(
        "finance.payment.failed",
        NotificationCategory.FINANCE,
        "Pago fallido",
        _payment_failed,
        "/activity",
        priority=NotificationPriority.HIGH,
        payload_fields=("payment_intent_id", "amount", "currency", "provider", "failure_message"),
    ),
    EventNames.PAYMENT_INTENT_REVERSED: _definition(
        "finance.payment.reversed",
        NotificationCategory.FINANCE,
        "Pago revertido",
        lambda payload: f"El pago por {_money(payload)} fue revertido.",
        "/activity",
        priority=NotificationPriority.HIGH,
        payload_fields=("payment_intent_id", "amount", "currency", "provider"),
    ),
    EventNames.PAYMENT_INTENT_CANCELLED: _definition(
        "finance.payment.cancelled",
        NotificationCategory.FINANCE,
        "Pago cancelado",
        lambda payload: f"El pago por {_money(payload)} fue cancelado.",
        "/activity",
        payload_fields=("payment_intent_id", "amount", "currency", "provider"),
    ),
    EventNames.PAYMENT_INTENT_DISPUTED: _definition(
        "finance.payment.disputed",
        NotificationCategory.FINANCE,
        "Pago en disputa",
        "El pago requiere seguimiento y conciliacion.",
        "/activity",
        priority=NotificationPriority.HIGH,
        payload_fields=("payment_intent_id", "amount", "currency", "provider"),
    ),
    EventNames.PAYMENT_RECURRING_TEMPLATE_CREATED: _definition(
        "reminder.scheduled_payment.created",
        NotificationCategory.REMINDER,
        "Pago programado creado",
        "Vexxo tendra en cuenta este compromiso en tu calendario financiero.",
        "/recurring-payments",
        payload_fields=("payment_template_id", "name", "next_run_at"),
    ),
    EventNames.PAYMENT_RECURRING_TEMPLATE_ACTIVATED: _definition(
        "reminder.scheduled_payment.activated",
        NotificationCategory.REMINDER,
        "Pago programado activado",
        "El compromiso volvera a incluirse en tus proximos vencimientos.",
        "/recurring-payments",
        payload_fields=("payment_template_id", "name", "next_run_at"),
    ),
    EventNames.PAYMENT_RECURRING_TEMPLATE_DEACTIVATED: _definition(
        "reminder.scheduled_payment.deactivated",
        NotificationCategory.REMINDER,
        "Pago programado pausado",
        "No se generaran nuevas corridas hasta que vuelvas a activarlo.",
        "/recurring-payments",
        payload_fields=("payment_template_id", "name"),
    ),
    EventNames.DEBT_CREATED: _definition(
        "finance.debt.created",
        NotificationCategory.FINANCE,
        "Deuda registrada",
        "El calendario de cuotas ya esta disponible para seguimiento.",
        "/debts",
        priority=NotificationPriority.LOW,
        payload_fields=("debt_id", "currency", "total_installments", "status"),
    ),
    EventNames.DEBT_PAYMENT_APPLIED: _definition(
        "finance.debt.payment_applied",
        NotificationCategory.FINANCE,
        "Pago aplicado a deuda",
        lambda payload: f"El abono por {_money(payload)} actualizo el saldo de tu deuda.",
        "/debts",
        payload_fields=("debt_id", "installment_id", "amount", "currency", "status"),
    ),
    EventNames.DEBT_STATUS_CHANGED: _definition(
        "finance.debt.status_changed",
        NotificationCategory.FINANCE,
        "Estado de deuda actualizado",
        lambda payload: f"La deuda ahora esta en estado {payload.get('status') or 'actualizado'}.",
        "/debts",
        payload_fields=("debt_id", "status", "previous_status"),
    ),
    EventNames.DEBT_OVERDUE_REFRESHED: _definition(
        "reminder.debt.overdue",
        NotificationCategory.REMINDER,
        "Cuota vencida",
        "Una deuda tiene cuotas vencidas que requieren revision.",
        "/debts",
        priority=NotificationPriority.HIGH,
        payload_fields=("debt_id", "overdue_count", "status"),
    ),
    "debts.debt.restructured.v1": _definition(
        "finance.debt.restructured",
        NotificationCategory.FINANCE,
        "Deuda reestructurada",
        "El nuevo calendario quedo guardado sin borrar los pagos historicos.",
        "/debts",
        priority=NotificationPriority.HIGH,
        payload_fields=("debt_id", "restructuring_id", "status"),
    ),
    EventNames.GOAL_CREATED: _definition(
        "finance.goal.created",
        NotificationCategory.FINANCE,
        "Meta creada",
        "Tu objetivo ya esta listo para recibir aportes.",
        "/goals-savings",
        priority=NotificationPriority.LOW,
        payload_fields=("goal_id", "target_amount", "currency", "status"),
    ),
    EventNames.GOAL_CONTRIBUTION_RECORDED: _definition(
        "finance.goal.contribution_recorded",
        NotificationCategory.FINANCE,
        "Aporte registrado",
        lambda payload: f"Se registraron {_money(payload)} en tu meta.",
        "/goals-savings",
        payload_fields=("goal_id", "contribution_id", "amount", "currency"),
    ),
    EventNames.GOAL_STATUS_CHANGED: _definition(
        "finance.goal.status_changed",
        NotificationCategory.FINANCE,
        "Estado de meta actualizado",
        lambda payload: f"Tu meta ahora esta en estado {payload.get('status') or 'actualizado'}.",
        "/goals-savings",
        payload_fields=("goal_id", "status", "previous_status"),
    ),
    EventNames.GOAL_CONTRIBUTION_REVERSED: _definition(
        "finance.goal.contribution_reversed",
        NotificationCategory.FINANCE,
        "Aporte revertido",
        "El progreso de la meta fue recalculado conservando la trazabilidad.",
        "/goals-savings",
        priority=NotificationPriority.HIGH,
        payload_fields=("goal_id", "contribution_id", "amount"),
    ),
    "goals.milestone.achieved.v1": _definition(
        "finance.goal.milestone_achieved",
        NotificationCategory.FINANCE,
        "Nuevo logro en tu meta",
        "Alcanzaste un nuevo hito de ahorro.",
        "/goals-savings",
        payload_fields=("goal_id", "milestone_id", "threshold_percent"),
    ),
    EventNames.ALERT_CREATED: _definition(
        "system.alert.created",
        NotificationCategory.REMINDER,
        "Tienes una alerta nueva",
        "Vexxo detecto una situacion que requiere tu atencion.",
        "/alerts",
        priority=NotificationPriority.HIGH,
        payload_fields=("alert_id", "type", "category", "severity", "source"),
    ),
    EventNames.DOCUMENT_OCR_COMPLETED: _definition(
        "system.document.ocr_completed",
        NotificationCategory.SYSTEM,
        "Documento procesado",
        "La lectura del documento termino y ya puedes revisar el resultado.",
        "/activity",
        priority=NotificationPriority.LOW,
        payload_fields=("document_id", "ocr_request_id", "engine"),
    ),
    EventNames.DOCUMENT_OCR_REVIEW_REQUIRED: _definition(
        "system.document.ocr_review_required",
        NotificationCategory.SYSTEM,
        "Documento pendiente de revision",
        "No fue posible completar la lectura automaticamente; revisa los datos del documento.",
        "/activity",
        priority=NotificationPriority.HIGH,
        payload_fields=("document_id", "ocr_request_id", "engine"),
    ),
}


def resolve_notification_definition(event_type: str) -> NotificationDefinition | None:
    return NOTIFICATION_CATALOG.get(str(event_type or ""))


def notification_catalog_snapshot() -> list[dict]:
    return [
        {
            "event_type": event_type,
            "notification_key": definition.key,
            "category": definition.category,
            "priority": definition.priority,
            "template_version": definition.version,
            "action_path": definition.action_path,
        }
        for event_type, definition in sorted(NOTIFICATION_CATALOG.items())
    ]


def minimized_notification_payload(definition: NotificationDefinition, event: VexxoAppDomainEvent) -> dict:
    source = event.payload or {}
    return {
        key: source[key]
        for key in definition.payload_fields
        if key in source and source[key] not in (None, "")
    }
