"""
Facade publica de serializers del agregado Account.

La implementacion real se reparte por verticales para mantener contratos sin
cargar toda la logica en un solo archivo.
"""

from .account_external_link_serializers import AccountExternalLinkSerializer
from .account_lifecycle_serializers import AccountReasonActionSerializer, AccountRecalcSerializer
from .account_plan_serializers import AccountPlanUsageSerializer
from .account_read_serializers import (
    AccountDetailSerializer,
    AccountListSerializer,
    AccountSerializer,
    AccountSummarySerializer,
)
from .account_sync_serializers import (
    AccountSyncErrorSerializer,
    AccountSyncRunningSerializer,
    AccountSyncScheduleSerializer,
    AccountSyncSuccessSerializer,
)
from .account_write_serializers import AccountWriteSerializer

__all__ = [
    "AccountDetailSerializer",
    "AccountExternalLinkSerializer",
    "AccountListSerializer",
    "AccountPlanUsageSerializer",
    "AccountReasonActionSerializer",
    "AccountRecalcSerializer",
    "AccountSerializer",
    "AccountSyncErrorSerializer",
    "AccountSyncRunningSerializer",
    "AccountSyncScheduleSerializer",
    "AccountSyncSuccessSerializer",
    "AccountSummarySerializer",
    "AccountWriteSerializer",
]
