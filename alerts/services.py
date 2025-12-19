from datetime import date, timedelta
from django.utils import timezone

from alerts.models import Alert
from transactions.Models import ScheduledPayment


def upsert_alert(owner, type_: str, key: str, payload: dict):
    # Idempotencia sin nuevos campos: busca por owner+type y clave en payload
    obj = None
    for a in Alert.objects.filter(owner=owner, type=type_).order_by('-created_at'):
        try:
            if str(a.payload.get('pago_programado_id')) == str(key):
                obj = a
                break
        except Exception:
            continue
    changed = False
    if obj is None:
        obj = Alert.objects.create(owner=owner, type=type_, payload=payload)
        changed = True
    elif obj.payload != payload:
        obj.payload = payload
        obj.save(update_fields=['payload'])
        changed = True
    return obj, changed


def generate_scheduled_payment_alerts(reference: date | None = None):
    if reference is None:
        reference = timezone.now().date()
    soon = reference + timedelta(days=3)

    qs = ScheduledPayment.objects.select_related('vendor', 'account').filter(status='pending')

    for sp in qs:
        kind = None
        titulo = None
        if sp.due_date < reference:
            kind = 'payment_overdue'
            titulo = 'Pago vencido'
        elif sp.due_date <= soon:
            kind = 'payment_due_soon'
            titulo = 'Pago por vencer'
        if not kind:
            continue
        payload = {
            'pago_programado_id': sp.id,
            'titulo': titulo,
            'nombre': sp.name,
            'monto': str(sp.amount),
            'fecha_vencimiento': sp.due_date.isoformat(),
            'prioridad': sp.priority,
            'proveedor': getattr(sp.vendor, 'name', None),
            'cuenta': getattr(sp.account, 'id', None),
        }
        upsert_alert(sp.owner, kind, key=str(sp.id), payload=payload)
