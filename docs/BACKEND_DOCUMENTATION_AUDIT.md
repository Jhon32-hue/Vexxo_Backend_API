# Inventario documental del backend

Generado desde el codigo del checkout; regenerar con `scripts/audit_backend_docs.py`.
Se revisa el alcance de cada README de dominio, incluidos submodulos.
Un diagrama de imports es evidencia estructural; el flujo de negocio se explica en
[BACKEND_CURRENT_FLOW.md](BACKEND_CURRENT_FLOW.md).

README de dominio inventariados: **98**.

| Modulo | Archivos de implementacion | Diagramas Mermaid |
| --- | ---: | ---: |
| [admin_tools/alert_review](../admin_tools/alert_review/README.md) | 5 | 1 |
| [admin_tools/audit_trails](../admin_tools/audit_trails/README.md) | 5 | 1 |
| [admin_tools/dashboards](../admin_tools/dashboards/README.md) | 7 | 1 |
| [admin_tools/manual_adjustments](../admin_tools/manual_adjustments/README.md) | 5 | 1 |
| [admin_tools](../admin_tools/README.md) | 30 | 1 |
| [admin_tools/user_lookup](../admin_tools/user_lookup/README.md) | 8 | 1 |
| [alerts/ai_stub](../alerts/ai_stub/README.md) | 5 | 1 |
| [alerts/alerts](../alerts/alerts/README.md) | 24 | 6 |
| [alerts/listeners](../alerts/listeners/README.md) | 5 | 1 |
| [alerts](../alerts/README.md) | 48 | 2 |
| [alerts/rules](../alerts/rules/README.md) | 8 | 1 |
| [alerts/triggers](../alerts/triggers/README.md) | 5 | 1 |
| [api/mobile](../api/mobile/README.md) | 12 | 1 |
| [api](../api/README.md) | 23 | 1 |
| [api/throttling](../api/throttling/README.md) | 5 | 1 |
| [api/v1](../api/v1/README.md) | 6 | 1 |
| [backend](../backend/README.md) | 5 | 1 |
| [common](../common/README.md) | 17 | 3 |
| [contacts/models](../contacts/models/README.md) | 2 | 1 |
| [contacts](../contacts/README.md) | 10 | 1 |
| [contacts/serializers](../contacts/serializers/README.md) | 2 | 1 |
| [contacts/views](../contacts/views/README.md) | 2 | 1 |
| [documents/files](../documents/files/README.md) | 13 | 1 |
| [documents/links_to_transactions](../documents/links_to_transactions/README.md) | 7 | 1 |
| [documents/metadata](../documents/metadata/README.md) | 5 | 1 |
| [documents/ocr_requests](../documents/ocr_requests/README.md) | 10 | 1 |
| [documents](../documents/README.md) | 40 | 1 |
| [documents/storage](../documents/storage/README.md) | 5 | 1 |
| [finance/accounts](../finance/accounts/README.md) | 76 | 6 |
| [finance/budgets](../finance/budgets/README.md) | 18 | 2 |
| [finance/categories](../finance/categories/README.md) | 8 | 1 |
| [finance/debts](../finance/debts/README.md) | 17 | 3 |
| [finance/fx](../finance/fx/README.md) | 8 | 1 |
| [finance/investments](../finance/investments/README.md) | 12 | 1 |
| [finance/limits](../finance/limits/README.md) | 5 | 1 |
| [finance](../finance/README.md) | 204 | 2 |
| [finance/transactions](../finance/transactions/README.md) | 51 | 8 |
| [finance/vendors](../finance/vendors/README.md) | 9 | 1 |
| [identity/consents](../identity/consents/README.md) | 13 | 2 |
| [identity/devices](../identity/devices/README.md) | 15 | 2 |
| [identity/eventing](../identity/eventing/README.md) | 11 | 2 |
| [identity/permissions](../identity/permissions/README.md) | 12 | 2 |
| [identity](../identity/README.md) | 103 | 2 |
| [identity/sessions](../identity/sessions/README.md) | 13 | 2 |
| [identity/social_identities](../identity/social_identities/README.md) | 4 | 1 |
| [identity/users](../identity/users/README.md) | 35 | 8 |
| [integrations/credentials](../integrations/credentials/README.md) | 5 | 1 |
| [integrations/open_banking](../integrations/open_banking/README.md) | 20 | 1 |
| [integrations/provider_mappings](../integrations/provider_mappings/README.md) | 0 | 1 |
| [integrations](../integrations/README.md) | 26 | 1 |
| [integrations_stub/banks](../integrations_stub/banks/README.md) | 8 | 1 |
| [integrations_stub/llm](../integrations_stub/llm/README.md) | 7 | 1 |
| [integrations_stub/messaging](../integrations_stub/messaging/README.md) | 2 | 1 |
| [integrations_stub](../integrations_stub/README.md) | 32 | 2 |
| [notifications/deliveries](../notifications/deliveries/README.md) | 7 | 1 |
| [notifications/listeners](../notifications/listeners/README.md) | 6 | 1 |
| [notifications/preferences](../notifications/preferences/README.md) | 8 | 2 |
| [notifications](../notifications/README.md) | 28 | 2 |
| [notifications/templates](../notifications/templates/README.md) | 6 | 1 |
| [observability](../observability/README.md) | 16 | 1 |
| [payments/calendar](../payments/calendar/README.md) | 5 | 1 |
| [payments/payment_intents](../payments/payment_intents/README.md) | 27 | 3 |
| [payments](../payments/README.md) | 51 | 2 |
| [payments/reminders](../payments/reminders/README.md) | 5 | 1 |
| [payments/scheduled_payments](../payments/scheduled_payments/README.md) | 14 | 4 |
| [planning/goals](../planning/goals/README.md) | 12 | 1 |
| [planning/milestones](../planning/milestones/README.md) | 5 | 1 |
| [planning/projections](../planning/projections/README.md) | 5 | 1 |
| [planning](../planning/README.md) | 30 | 2 |
| [planning/shared_goals](../planning/shared_goals/README.md) | 8 | 1 |
| [realtime/consumers](../realtime/consumers/README.md) | 6 | 2 |
| [realtime](../realtime/README.md) | 11 | 2 |
| [reports/exports](../reports/exports/README.md) | 5 | 1 |
| [reports/monthly_reports](../reports/monthly_reports/README.md) | 7 | 1 |
| [reports](../reports/README.md) | 31 | 2 |
| [reports/reports](../reports/reports/README.md) | 9 | 1 |
| [reports/snapshots](../reports/snapshots/README.md) | 5 | 1 |
| [reports/summaries](../reports/summaries/README.md) | 5 | 1 |
| [security](../security/README.md) | 27 | 1 |
| [social/chat](../social/chat/README.md) | 5 | 1 |
| [social/contacts](../social/contacts/README.md) | 5 | 1 |
| [social/documents_shared](../social/documents_shared/README.md) | 5 | 1 |
| [social/groups](../social/groups/README.md) | 5 | 1 |
| [social/invitations](../social/invitations/README.md) | 8 | 1 |
| [social/memberships](../social/memberships/README.md) | 5 | 1 |
| [social](../social/README.md) | 53 | 1 |
| [social/shared_expenses](../social/shared_expenses/README.md) | 9 | 2 |
| [social/teams](../social/teams/README.md) | 11 | 1 |
| [support/access_history](../support/access_history/README.md) | 5 | 1 |
| [support/audit](../support/audit/README.md) | 11 | 1 |
| [support/consent_audit](../support/consent_audit/README.md) | 5 | 1 |
| [support](../support/README.md) | 26 | 2 |
| [support/support_views](../support/support_views/README.md) | 5 | 1 |
| [tasks/dispatchers](../tasks/dispatchers/README.md) | 3 | 1 |
| [tasks/listeners](../tasks/listeners/README.md) | 5 | 1 |
| [tasks](../tasks/README.md) | 36 | 1 |
| [tasks/scheduled](../tasks/scheduled/README.md) | 14 | 1 |
| [tasks/workers](../tasks/workers/README.md) | 8 | 1 |

## Archivos que requieren revision

- `realtime/redis_channels.py`: linea 5: invalid syntax.
- `realtime/routing.py`: linea 5: invalid syntax.
- `realtime/typing.py`: linea 5: invalid syntax.
- `realtime/unread_counters.py`: linea 5: invalid syntax.

## Catalogos ejecutables

- Outboxes: `accounts`, `transactions`, `alerts`, `identity`, `payments`, `debts`, `goals`, `documents`, `shared_expenses`.
- Workers: `accounts.sync`, `accounts.intelligence`, `alerts.ai`, `transactions.voice`, `documents.ocr`, `security.key_rotation`.
- Jobs: `open_banking.retry_syncs`, `open_banking.expire_consents`, `open_banking.purge_payloads`, `identity.expire_attestations`, `security.purge_retention`, `documents.migrate_encryption`, `documents.purge_expired`, `reports.process_exports`, `reports.purge_exports`, `debts.refresh_overdue`, `payments.process_schedule_runs`.

## Limites de la auditoria

El analisis AST no importa Django ni lee archivos .env. No verifica callbacks externos,
renderizado Mermaid, estado de PostgreSQL ni disponibilidad cloud. Los imports relativos,
acciones dinamicas de DRF y modelos con bases no convencionales requieren lectura contextual.
La narrativa historica no se considera certificada por la huella del inventario.
