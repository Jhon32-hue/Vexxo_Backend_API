# audit/helpers.py

from typing import Optional, Dict, Any
from support.audit.models.audit import AuditLog
import logging

logger = logging.getLogger(__name__)


def audit_log(
    *,
    user=None,
    module: str,
    action: str,
    entity: str,
    entity_id: Optional[str | int] = None,
    source: AuditLog.Source = AuditLog.Source.USER,
    impact: AuditLog.Impact = AuditLog.Impact.LOW,
    description: str = "",
    diff: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    silent: bool = False,
) -> Optional[AuditLog]:
    """
    Punto único para registrar auditoría en Vexxo_app.

    - Centraliza toda la creación de AuditLog
    - Evita duplicación de lógica
    - Preparado para async / colas / webhooks
    """

    try:
        return AuditLog.objects.create(
            user=user,
            module=module,
            action=action,
            source=source,
            impact=impact,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            description=description,
            diff=diff or {},
            metadata=metadata or {},
        )

    except Exception as exc:
        # Nunca romper el flujo del negocio por auditoría
        logger.exception("Audit log failed", extra={
            "module": module,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
        })

        if not silent:
            raise

        return None
