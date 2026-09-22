import base64
import os
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from finance.accounts.models import Account
from finance.transactions.Models import Transaction
from reports.reports.services import (
    consume_report_export,
    create_report_snapshot,
    process_report_exports,
    purge_report_exports,
    queue_report_export,
)


def _key():
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


@override_settings(SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION="v1", SECURITY_ENCRYPTION_KEYS={"v1": _key()})
class ReportSnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="report-owner", email="report@example.com", password="TestPass2026!")
        self.other = User.objects.create_user(username="report-other", email="other-report@example.com", password="TestPass2026!")
        self.account = Account.objects.create(owner=self.user, name="Main", currency="COP")
        other_account = Account.objects.create(owner=self.other, name="Other", currency="COP")
        Transaction.objects.create(owner=self.user, account=self.account, type="income", amount="100.00", date=date(2026, 9, 1))
        Transaction.objects.create(owner=self.user, account=self.account, type="expense", amount="30.00", date=date(2026, 9, 2))
        Transaction.objects.create(owner=self.other, account=other_account, type="income", amount="999.00", date=date(2026, 9, 1))

    def test_snapshot_is_owner_scoped_and_immutable(self):
        snapshot, created = create_report_snapshot(owner=self.user, report_type="cashflow", period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), currency="COP", timezone_name="America/Bogota", idempotency_key="report-1")
        self.assertTrue(created)
        self.assertEqual(snapshot.payload["data"], {"income": "100.00", "expenses": "30.00", "net": "70.00"})
        snapshot.currency = "USD"
        with self.assertRaises(ValueError):
            snapshot.save()

    def test_export_is_encrypted_and_downloads_once(self):
        snapshot, _ = create_report_snapshot(owner=self.user, report_type="cashflow", period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), currency="COP", timezone_name="America/Bogota", idempotency_key="report-2")
        export, token = queue_report_export(owner=self.user, snapshot=snapshot, export_format="json")
        self.assertEqual(process_report_exports()["processed"], 1)
        export.refresh_from_db()
        self.assertNotIn(b'"income": "100.00"', bytes(export.encrypted_content))
        _export, content = consume_report_export(export_id=export.pk, owner=self.user, token=token)
        self.assertIn(b'"income": "100.00"', content)
        with self.assertRaises(Exception):
            consume_report_export(export_id=export.pk, owner=self.user, token=token)

    @override_settings(REPORT_EXPORT_DOWNLOADED_RETENTION_HOURS=0)
    def test_downloaded_export_body_is_purged_but_audit_hash_remains(self):
        snapshot, _ = create_report_snapshot(owner=self.user, report_type="cashflow", period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), currency="COP", timezone_name="America/Bogota", idempotency_key="report-purge")
        export, token = queue_report_export(owner=self.user, snapshot=snapshot, export_format="json")
        process_report_exports()
        consume_report_export(export_id=export.pk, owner=self.user, token=token)
        summary = purge_report_exports()
        export.refresh_from_db()
        self.assertEqual(summary["purged"], 1)
        self.assertEqual(bytes(export.encrypted_content), b"")
        self.assertEqual(export.encryption_envelope, {})
        self.assertTrue(export.content_purged_at)
        self.assertEqual(len(export.plaintext_sha256), 64)
