from enum import StrEnum
from dataclasses import dataclass, replace


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ValidationBoundary(StrEnum):
    MODEL = "model"
    SERVICE = "service"
    INTERNAL = "internal"


class JsonValidatorProfile(StrEnum):
    SAFE_METADATA = "safe_metadata"
    EXTERNAL_PAYLOAD = "external_payload"
    INTERNAL_JSON = "internal_json"


DEFAULT_RETENTION_DAYS = {
    DataClassification.PUBLIC: 3650,
    DataClassification.INTERNAL: 730,
    DataClassification.CONFIDENTIAL: 365,
    DataClassification.RESTRICTED: 90,
}

SENSITIVE_METADATA_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "authorization",
        "client_secret",
        "api_key",
        "password",
        "secret",
        "private_key",
        "credential",
        "cvv",
        "pin",
    }
)


class UnregisteredJsonFieldPolicy(LookupError):
    pass


# Security review snapshot. A new JSONField must be acknowledged here so CI
# cannot silently assign policy from its name alone.
REVIEWED_JSON_FIELDS = frozenset(
    {
        "accounts.Account.badges",
        "accounts.Account.provider_metadata",
        "accounts.Account.sync_runtime",
        "accounts.AccountBalanceFallback.affected_account_ids",
        "accounts.AccountBalanceFallback.metadata",
        "accounts.AccountInvitation.metadata",
        "accounts.AccountMembership.metadata",
        "accounts.AccountPortfolioSnapshot.balances_by_currency",
        "accounts.AccountPortfolioSnapshot.counts_by_currency",
        "accounts.AccountPortfolioSnapshot.counts_by_type",
        "accounts.AccountPortfolioSnapshot.ownership_distribution",
        "accounts.AccountProductSignal.evidence",
        "accounts.AccountProductSignal.signal_value",
        "accounts.AccountRiskSnapshot.supporting_factors",
        "accounts.DomainEventOutbox.metadata",
        "accounts.DomainEventOutbox.payload",
        "alerts.Alert.ai_tags",
        "alerts.Alert.payload",
        "alerts.AlertDomainEventOutbox.metadata",
        "alerts.AlertDomainEventOutbox.payload",
        "audit.AuditLog.diff",
        "audit.AuditLog.metadata",
        "budgets.Budget.alert_thresholds",
        "budgets.SharedBudget.alert_thresholds",
        "consents.UserConsent.data_categories",
        "consents.UserConsent.metadata",
        "debts.DebtDomainEventOutbox.metadata",
        "debts.DebtDomainEventOutbox.payload",
        "debts.DebtRestructuring.previous_terms",
        "debts.DebtRestructuring.new_terms",
        "debts.DebtRestructuring.replaced_installment_ids",
        "debts.DebtRestructuring.created_installment_ids",
        "devices.UserDevice.metadata",
        "exports.ReportExport.encryption_envelope",
        "files.DocumentFile.encryption_envelope",
        "fx.ExchangeRate.metadata",
        "goals.Goal.strategy",
        "goals.GoalDomainEventOutbox.metadata",
        "goals.GoalDomainEventOutbox.payload",
        "identity_eventing.IdentityDomainEventOutbox.metadata",
        "identity_eventing.IdentityDomainEventOutbox.payload",
        "identity_permissions.UserPermissionGrant.metadata",
        "identity_sessions.UserSession.metadata",
        "integration_credentials.IntegrationCredential.encrypted_payload",
        "integration_credentials.IntegrationCredential.safe_metadata",
        "metadata.DocumentMetadata.attributes",
        "notification_deliveries.NotificationDelivery.payload",
        "ocr_requests.DocumentDomainEventOutbox.metadata",
        "ocr_requests.DocumentDomainEventOutbox.payload",
        "ocr_requests.OcrRequest.client_structured_hint",
        "ocr_requests.OcrRequest.structured_data",
        "open_banking.OpenBankingConnection.safe_metadata",
        "open_banking.OpenBankingExternalPayload.safe_metadata",
        "open_banking.OpenBankingExternalPayload.sanitized_payload",
        "open_banking.OpenBankingReconciliationIssue.safe_metadata",
        "open_banking.OpenBankingSyncRun.safe_metadata",
        "open_banking.OpenBankingTimelineEvent.safe_metadata",
        "open_banking.OpenBankingConnection.scopes",
        "open_banking.OpenBankingWebhookReceipt.safe_metadata",
        "payment_intents.PaymentDomainEventOutbox.metadata",
        "payment_intents.PaymentDomainEventOutbox.payload",
        "payment_intents.PaymentIntent.command_payload",
        "payment_intents.PaymentIntent.destination_payload",
        "payment_intents.PaymentIntent.fee_breakdown",
        "payment_intents.PaymentIntent.pricing_snapshot",
        "payment_intents.PaymentIntent.provider_metadata",
        "payment_intents.PaymentIntent.tax_breakdown",
        "payment_intents.PaymentOperationalCase.details",
        "payment_intents.PaymentProviderCallbackReceipt.normalized_payload",
        "payment_intents.PaymentProviderCallbackReceipt.raw_headers",
        "payment_intents.PaymentProviderCallbackReceipt.raw_payload",
        "payment_intents.PaymentSettlementRecord.fee_snapshot",
        "payment_intents.PaymentSettlementRecord.settlement_payload",
        "payment_intents.PayoutBatch.pricing_snapshot",
        "payment_intents.PayoutBatch.provider_metadata",
        "payment_intents.PayoutInstruction.fee_breakdown",
        "payment_intents.PayoutInstruction.provider_metadata",
        "payment_intents.PayoutInstruction.tax_breakdown",
        "realtime_consumers.RealtimeSignal.payload",
        "rules.Rule.conditions",
        "rules.Rule.effects",
        "scheduled_payments.PaymentScheduleRun.run_payload",
        "scheduled_payments.PaymentTemplate.execution_defaults",
        "security.SecurityAuditEvent.safe_metadata",
        "snapshots.ReportSnapshot.payload",
        "social_identities.SocialAuthHandoff.metadata",
        "social_identities.UserSocialIdentity.metadata",
        "socialaccount.SocialAccount.extra_data",
        "socialaccount.SocialApp.settings",
        "shared_expenses.SharedExpenseDomainEventOutbox.metadata",
        "shared_expenses.SharedExpenseDomainEventOutbox.payload",
        "task_scheduled.ScheduledJobState.last_result",
        "transactions.Transaction.comments",
        "transactions.Transaction.components",
        "transactions.Transaction.raw_payload",
        "transactions.TransactionDomainEventOutbox.metadata",
        "transactions.TransactionDomainEventOutbox.payload",
        "transactions.TransactionExternalDetails.transaction_information",
        "transactions.TransactionFieldProvenance.current_value",
        "transactions.TransactionFieldProvenance.previous_value",
        "transactions.TransactionInferenceRequest.normalized_payload",
        "transactions.TransactionInferenceRequest.raw_payload",
        "transactions.TransactionInferenceRequest.result_summary",
        "transactions.TransactionIntakeBatch.raw_summary",
        "transactions.TransactionIntakeReceipt.normalized_payload",
        "transactions.TransactionIntakeReceipt.raw_payload",
        "transactions.TransactionReconciliationIssue.details",
        "transactions.TransactionReconciliationIssue.resolution_payload",
        "transactions.TransactionSourceLink.last_normalized_payload",
        "users.UserAuthChallenge.metadata",
        "users.UserMfaMethod.recovery_code_hashes",
        "users.UserOnboardingProfile.income_sources",
        "users.UserOnboardingProfile.preferred_currencies",
        "users.UserOnboardingProfile.use_cases",
        "access_history.SupportAccessRecord.safe_metadata",
    }
)


@dataclass(frozen=True)
class JsonFieldPolicy:
    classification: DataClassification
    schema: str
    retention_days: int | None
    redact_on_read: bool
    erasable: bool
    external_input: bool
    validation_boundary: ValidationBoundary = ValidationBoundary.INTERNAL
    validator_profile: JsonValidatorProfile = JsonValidatorProfile.INTERNAL_JSON
    max_bytes: int = 131_072


# Model validators are the last line of defense for values written outside the
# canonical service. Service fields are validated/sanitized at their ingress.
# Every other reviewed field is application-produced and is never an external
# write boundary.
MODEL_VALIDATED_JSON_FIELDS = frozenset(
    {
        "devices.UserDevice.metadata",
        "integration_credentials.IntegrationCredential.safe_metadata",
        "open_banking.OpenBankingConnection.safe_metadata",
        "open_banking.OpenBankingExternalPayload.safe_metadata",
        "open_banking.OpenBankingExternalPayload.sanitized_payload",
        "open_banking.OpenBankingReconciliationIssue.safe_metadata",
        "open_banking.OpenBankingSyncRun.safe_metadata",
        "open_banking.OpenBankingTimelineEvent.safe_metadata",
        "open_banking.OpenBankingWebhookReceipt.safe_metadata",
        "security.SecurityAuditEvent.safe_metadata",
        "users.UserMfaMethod.recovery_code_hashes",
        "users.UserOnboardingProfile.income_sources",
        "users.UserOnboardingProfile.preferred_currencies",
        "users.UserOnboardingProfile.use_cases",
        "access_history.SupportAccessRecord.safe_metadata",
    }
)

SERVICE_VALIDATED_JSON_FIELDS = frozenset(
    {
        "accounts.Account.provider_metadata",
        "accounts.AccountInvitation.metadata",
        "accounts.AccountMembership.metadata",
        "budgets.Budget.alert_thresholds",
        "budgets.SharedBudget.alert_thresholds",
        "consents.UserConsent.data_categories",
        "consents.UserConsent.metadata",
        "debts.DebtRestructuring.new_terms",
        "metadata.DocumentMetadata.attributes",
        "ocr_requests.OcrRequest.client_structured_hint",
        "fx.ExchangeRate.metadata",
        "goals.Goal.strategy",
        "identity_permissions.UserPermissionGrant.metadata",
        "identity_sessions.UserSession.metadata",
        "payment_intents.PaymentIntent.command_payload",
        "payment_intents.PaymentIntent.destination_payload",
        "payment_intents.PaymentProviderCallbackReceipt.raw_headers",
        "payment_intents.PaymentProviderCallbackReceipt.raw_payload",
        "payment_intents.PaymentOperationalCase.details",
        "rules.Rule.conditions",
        "rules.Rule.effects",
        "scheduled_payments.PaymentScheduleRun.run_payload",
        "scheduled_payments.PaymentTemplate.execution_defaults",
        "social_identities.SocialAuthHandoff.metadata",
        "social_identities.UserSocialIdentity.metadata",
        "socialaccount.SocialAccount.extra_data",
        "socialaccount.SocialApp.settings",
        "transactions.Transaction.comments",
        "transactions.Transaction.components",
        "transactions.Transaction.raw_payload",
        "transactions.TransactionExternalDetails.transaction_information",
        "transactions.TransactionInferenceRequest.raw_payload",
        "transactions.TransactionIntakeBatch.raw_summary",
        "transactions.TransactionIntakeReceipt.raw_payload",
        "transactions.TransactionReconciliationIssue.resolution_payload",
    }
)

SAFE_METADATA_MODEL_FIELDS = MODEL_VALIDATED_JSON_FIELDS - {
    "open_banking.OpenBankingExternalPayload.sanitized_payload",
}


_RESTRICTED_HINTS = ("raw", "payload", "credential", "token", "evidence", "attestation")
_INTERNAL_HINTS = ("result", "state", "config", "runtime", "dispatch")
_EXTERNAL_HINTS = ("metadata", "payload", "attributes", "request", "response", "details", "profile")


JSON_FIELD_POLICY_OVERRIDES: dict[str, JsonFieldPolicy] = {
    "security.SecurityAuditEvent.safe_metadata": JsonFieldPolicy(DataClassification.RESTRICTED, "security.audit.metadata.v1", 2555, True, False, False),
    "open_banking.OpenBankingConnection.safe_metadata": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "open_banking.connection.metadata.v1", 730, True, True, True),
    "open_banking.OpenBankingWebhookReceipt.safe_metadata": JsonFieldPolicy(DataClassification.RESTRICTED, "open_banking.webhook.metadata.v1", 730, True, False, True),
    "open_banking.OpenBankingExternalPayload.sanitized_payload": JsonFieldPolicy(DataClassification.RESTRICTED, "open_banking.quarantine.payload.v1", 30, True, True, True),
    "open_banking.OpenBankingExternalPayload.safe_metadata": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "open_banking.quarantine.metadata.v1", 365, True, True, False),
    "open_banking.OpenBankingSyncRun.safe_metadata": JsonFieldPolicy(DataClassification.INTERNAL, "open_banking.sync.metadata.v1", 730, False, False, False),
    "open_banking.OpenBankingTimelineEvent.safe_metadata": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "open_banking.timeline.metadata.v1", 730, True, False, False),
    "open_banking.OpenBankingReconciliationIssue.safe_metadata": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "open_banking.reconciliation.metadata.v1", 730, True, False, False),
    "access_history.SupportAccessRecord.safe_metadata": JsonFieldPolicy(DataClassification.RESTRICTED, "support.access.metadata.v1", 2555, True, False, False),
    "integration_credentials.IntegrationCredential.safe_metadata": JsonFieldPolicy(DataClassification.RESTRICTED, "integration.credential.metadata.v1", 730, True, True, True),
    "files.DocumentFile.encryption_envelope": JsonFieldPolicy(DataClassification.RESTRICTED, "security.encryption.envelope.v1", None, True, False, False),
    "exports.ReportExport.encryption_envelope": JsonFieldPolicy(DataClassification.RESTRICTED, "security.encryption.envelope.v1", 30, True, True, False),
    "debts.DebtRestructuring.previous_terms": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "debts.restructuring.terms.v1", 2555, True, False, False),
    "debts.DebtRestructuring.new_terms": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "debts.restructuring.terms.v1", 2555, True, False, False),
    "debts.DebtRestructuring.replaced_installment_ids": JsonFieldPolicy(DataClassification.INTERNAL, "debts.restructuring.ids.v1", 2555, False, False, False),
    "debts.DebtRestructuring.created_installment_ids": JsonFieldPolicy(DataClassification.INTERNAL, "debts.restructuring.ids.v1", 2555, False, False, False),
    "users.UserOnboardingProfile.income_sources": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "identity.onboarding.income_sources.v1", 365, True, True, True),
    "users.UserOnboardingProfile.preferred_currencies": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "identity.onboarding.preferred_currencies.v1", 365, True, True, True),
    "users.UserOnboardingProfile.use_cases": JsonFieldPolicy(DataClassification.CONFIDENTIAL, "identity.onboarding.use_cases.v1", 365, True, True, True),
}


def resolve_json_field_policy(model_label: str, field_name: str) -> JsonFieldPolicy:
    key = f"{model_label}.{field_name}"
    if key not in REVIEWED_JSON_FIELDS:
        raise UnregisteredJsonFieldPolicy(f"JSONField policy is not reviewed: {key}")
    if key in JSON_FIELD_POLICY_OVERRIDES:
        policy = JSON_FIELD_POLICY_OVERRIDES[key]
    else:
        normalized = field_name.lower()
        if any(hint in normalized for hint in _RESTRICTED_HINTS):
            classification = DataClassification.RESTRICTED
        elif any(hint in normalized for hint in _INTERNAL_HINTS):
            classification = DataClassification.INTERNAL
        else:
            classification = DataClassification.CONFIDENTIAL
        policy = JsonFieldPolicy(
            classification=classification,
            schema=f"{model_label.lower()}.{field_name}.v1",
            retention_days=DEFAULT_RETENTION_DAYS[classification],
            redact_on_read=classification in {DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED},
            erasable=classification != DataClassification.INTERNAL,
            external_input=False,
        )

    if key in MODEL_VALIDATED_JSON_FIELDS:
        boundary = ValidationBoundary.MODEL
    elif key in SERVICE_VALIDATED_JSON_FIELDS:
        boundary = ValidationBoundary.SERVICE
    else:
        boundary = ValidationBoundary.INTERNAL

    if key in SAFE_METADATA_MODEL_FIELDS:
        profile = JsonValidatorProfile.SAFE_METADATA
        max_bytes = 16_384
    elif boundary in {ValidationBoundary.MODEL, ValidationBoundary.SERVICE}:
        profile = JsonValidatorProfile.EXTERNAL_PAYLOAD
        max_bytes = 131_072
    else:
        profile = JsonValidatorProfile.INTERNAL_JSON
        max_bytes = 131_072

    return replace(
        policy,
        external_input=boundary != ValidationBoundary.INTERNAL,
        validation_boundary=boundary,
        validator_profile=profile,
        max_bytes=max_bytes,
    )
