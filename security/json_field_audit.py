from __future__ import annotations

from django.apps import apps
from django.db import models
from django.core.exceptions import ValidationError

from security.policies import (
    JsonValidatorProfile,
    UnregisteredJsonFieldPolicy,
    ValidationBoundary,
    resolve_json_field_policy,
)
from security.validators import validate_external_payload, validate_safe_metadata


EXTERNAL_FIELD_HINTS = {"metadata", "payload", "attributes", "raw", "response", "request", "details"}


def audit_json_fields(*, scan_data: bool = False, limit_per_field: int = 100) -> dict:
    rows = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not isinstance(field, models.JSONField):
                continue
            validators = [getattr(validator, "__name__", validator.__class__.__name__) for validator in field.validators]
            name = f"{model._meta.label}.{field.name}"
            likely_external = any(hint in field.name.lower() for hint in EXTERNAL_FIELD_HINTS)
            try:
                policy = resolve_json_field_policy(model._meta.label, field.name)
            except UnregisteredJsonFieldPolicy:
                rows.append(
                    {
                        "field": name,
                        "classification": None,
                        "schema": None,
                        "retention_days": None,
                        "redact_on_read": None,
                        "erasable": None,
                        "external_input": None,
                        "validation_boundary": None,
                        "validator_profile": None,
                        "max_bytes": None,
                        "likely_external": likely_external,
                        "validators": validators,
                        "has_safe_metadata_validator": "validate_safe_metadata" in validators,
                        "reviewed": False,
                    }
                )
                continue
            row = {
                "field": name,
                "classification": policy.classification.value,
                "schema": policy.schema,
                "retention_days": policy.retention_days,
                "redact_on_read": policy.redact_on_read,
                "erasable": policy.erasable,
                "external_input": policy.external_input,
                "validation_boundary": policy.validation_boundary.value,
                "validator_profile": policy.validator_profile.value,
                "max_bytes": policy.max_bytes,
                "likely_external": likely_external,
                "validators": validators,
                "has_safe_metadata_validator": "validate_safe_metadata" in validators,
                "reviewed": True,
            }
            expected_model_validator = {
                JsonValidatorProfile.SAFE_METADATA: "validate_safe_metadata",
                JsonValidatorProfile.EXTERNAL_PAYLOAD: "validate_external_payload",
            }.get(policy.validator_profile)
            row["policy_errors"] = []
            if policy.validation_boundary == ValidationBoundary.MODEL and expected_model_validator not in validators:
                row["policy_errors"].append(f"missing_model_validator:{expected_model_validator}")
            if policy.validation_boundary == ValidationBoundary.INTERNAL and policy.external_input:
                row["policy_errors"].append("internal_field_marked_external")
            if scan_data:
                checked = invalid = 0
                for value in model._default_manager.exclude(**{field.name: None}).values_list(field.name, flat=True)[:max(1, limit_per_field)]:
                    checked += 1
                    try:
                        validator = (
                            validate_safe_metadata
                            if policy.validator_profile == JsonValidatorProfile.SAFE_METADATA
                            else validate_external_payload
                        )
                        validator(value, max_bytes=policy.max_bytes)
                    except ValidationError:
                        invalid += 1
                row.update(rows_checked=checked, invalid_rows=invalid)
            rows.append(row)
    risky = [row for row in rows if row["likely_external"] and not row["has_safe_metadata_validator"]]
    unreviewed = [row for row in rows if not row["reviewed"]]
    unreviewed_external = [row for row in unreviewed if row["likely_external"]]
    policy_errors = [row for row in rows if row.get("policy_errors")]
    return {
        "total_json_fields": len(rows),
        "classified_fields": len(rows) - len(unreviewed),
        "unclassified_fields": len(unreviewed),
        "unreviewed_external_fields": len(unreviewed_external),
        "policy_error_fields": len(policy_errors),
        "advisory_name_candidates_without_model_validator": len(risky),
        "invalid_rows": sum(row.get("invalid_rows", 0) for row in rows),
        "fields": rows,
    }
