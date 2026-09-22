from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from finance.debts.services import refresh_overdue_installments
from payments.scheduled_payments.services import process_due_schedule_runs
from reports.reports.services import process_report_exports, purge_report_exports
from documents.files.migration_service import migrate_historical_documents
from documents.files.services import purge_expired_documents
from security.retention import purge_security_retention
from identity.devices.services import expire_platform_attestations
from integrations.open_banking.lifecycle import (
    expire_open_banking_consents,
    purge_external_payloads,
    retry_due_open_banking_syncs,
)


@dataclass(frozen=True)
class ScheduledJobSpec:
    name: str
    interval_seconds: int
    runner: Callable[[], dict]


def _refresh_debt_overdue() -> dict:
    return {"updated_installments": refresh_overdue_installments()}


def _process_scheduled_payments() -> dict:
    return process_due_schedule_runs()


SCHEDULED_JOBS = {
    "open_banking.retry_syncs": ScheduledJobSpec(
        name="open_banking.retry_syncs",
        interval_seconds=30,
        runner=retry_due_open_banking_syncs,
    ),
    "open_banking.expire_consents": ScheduledJobSpec(
        name="open_banking.expire_consents",
        interval_seconds=3600,
        runner=expire_open_banking_consents,
    ),
    "open_banking.purge_payloads": ScheduledJobSpec(
        name="open_banking.purge_payloads",
        interval_seconds=86400,
        runner=purge_external_payloads,
    ),
    "identity.expire_attestations": ScheduledJobSpec(
        name="identity.expire_attestations",
        interval_seconds=3600,
        runner=expire_platform_attestations,
    ),
    "security.purge_retention": ScheduledJobSpec(
        name="security.purge_retention",
        interval_seconds=86400,
        runner=lambda: purge_security_retention(limit_per_model=500),
    ),
    "documents.migrate_encryption": ScheduledJobSpec(
        name="documents.migrate_encryption",
        interval_seconds=300,
        runner=lambda: migrate_historical_documents(limit=10),
    ),
    "documents.purge_expired": ScheduledJobSpec(
        name="documents.purge_expired",
        interval_seconds=86400,
        runner=purge_expired_documents,
    ),
    "reports.process_exports": ScheduledJobSpec(
        name="reports.process_exports",
        interval_seconds=15,
        runner=process_report_exports,
    ),
    "reports.purge_exports": ScheduledJobSpec(
        name="reports.purge_exports",
        interval_seconds=3600,
        runner=purge_report_exports,
    ),
    "debts.refresh_overdue": ScheduledJobSpec(
        name="debts.refresh_overdue",
        interval_seconds=60,
        runner=_refresh_debt_overdue,
    ),
    "payments.process_schedule_runs": ScheduledJobSpec(
        name="payments.process_schedule_runs",
        interval_seconds=60,
        runner=_process_scheduled_payments,
    ),
}
