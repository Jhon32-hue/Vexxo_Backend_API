from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class RuntimeObservabilityTests(TestCase):
    def test_health_and_readiness_are_public_and_return_request_id(self):
        health = self.client.get("/healthz/", HTTP_X_REQUEST_ID="local-check-1")
        readiness = self.client.get("/readyz/")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health["X-Request-ID"], "local-check-1")
        self.assertEqual(readiness.status_code, 200)
        self.assertTrue(readiness.json()["checks"]["database"]["ok"])

    def test_unsafe_request_id_is_replaced(self):
        response = self.client.get("/healthz/", HTTP_X_REQUEST_ID="unsafe value\n")

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response["X-Request-ID"], "unsafe value\n")
        self.assertEqual(len(response["X-Request-ID"]), 32)

    def test_operational_commands_support_empty_database(self):
        output = StringIO()
        call_command("runtime_status", stdout=output)
        call_command("outbox_status", stdout=output)
        call_command("worker_status", stdout=output)

        rendered = output.getvalue()
        self.assertIn("database_ok=True", rendered)
        self.assertIn("accounts: pending=0", rendered)
        self.assertIn("transactions.voice:", rendered)
