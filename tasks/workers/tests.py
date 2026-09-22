from unittest.mock import patch

from django.test import SimpleTestCase

from tasks.workers.management.commands.publish_outbox import Command


class PublishOutboxCommandTests(SimpleTestCase):
    @patch("tasks.workers.management.commands.publish_outbox.call_command")
    def test_wrapper_does_not_require_context_specific_loop_options(self, call_command_mock):
        Command().handle(
            context="payments",
            loop=False,
            sleep_seconds=5,
            limit=25,
            worker_id="local-payments",
        )

        call_command_mock.assert_called_once_with(
            "payments_publish_outbox",
            limit=25,
            worker_id="local-payments",
        )

    @patch("tasks.workers.management.commands.publish_outbox.time.sleep", side_effect=StopIteration)
    @patch("tasks.workers.management.commands.publish_outbox.call_command")
    def test_wrapper_owns_continuous_polling(self, call_command_mock, sleep_mock):
        with self.assertRaises(StopIteration):
            Command().handle(
                context="accounts",
                loop=True,
                sleep_seconds=7,
                limit=50,
                worker_id="local-accounts",
            )

        call_command_mock.assert_called_once_with(
            "accounts_publish_outbox",
            batch_size=50,
            worker_id="local-accounts",
        )
        sleep_mock.assert_called_once_with(7)

    @patch("tasks.workers.management.commands.publish_outbox.publish_pending_events")
    def test_catalog_supports_multiple_standard_outboxes(self, publish_pending_mock):
        publish_pending_mock.return_value = {"processed": 0, "failed": 0, "scanned": 0}

        Command().handle(
            context="debts,goals",
            loop=False,
            sleep_seconds=5,
            limit=25,
            worker_id="local-domain",
        )

        self.assertEqual(publish_pending_mock.call_count, 2)
