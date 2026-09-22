from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenBankingProvider:
    code: str
    name: str
    countries: tuple[str, ...]
    capabilities: tuple[str, ...]
    required_environment: tuple[str, ...]
    certification_prefix: str = ""
    local_only: bool = False
    implemented: bool = False

    @property
    def configured(self) -> bool:
        if self.local_only:
            return True
        return all(bool(os.getenv(key, "").strip()) for key in self.required_environment)

    @property
    def available(self) -> bool:
        return self.configured and self.certified and (self.local_only or self.implemented)

    @property
    def certified(self) -> bool:
        if self.local_only:
            return True
        if not self.certification_prefix:
            return False
        approved = os.getenv(f"{self.certification_prefix}_CERTIFIED", "").strip().lower() == "true"
        fixture_path = os.getenv(f"{self.certification_prefix}_OFFICIAL_FIXTURE_PATH", "").strip()
        expected_hash = os.getenv(f"{self.certification_prefix}_OFFICIAL_FIXTURE_SHA256", "").strip().lower()
        if not approved or not fixture_path or len(expected_hash) != 64:
            return False
        path = Path(fixture_path).expanduser()
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        return bool(
            hashlib.sha256(raw).hexdigest() == expected_hash
            and payload.get("fixture_type") == "official_sandbox_vector"
            and payload.get("provider") == self.code
            and payload.get("webhook_vectors")
        )

    def public_payload(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "countries": list(self.countries),
            "capabilities": list(self.capabilities),
            "configured": self.configured,
            "certified": self.certified,
            "available": self.available,
            "mode": "local_mock" if self.local_only else "provider",
        }


PROVIDERS = {
    provider.code: provider
    for provider in (
        OpenBankingProvider(
            code="local_mock",
            name="Banco local de desarrollo",
            countries=("CO",),
            capabilities=("accounts", "balances", "transactions", "webhooks"),
            required_environment=(),
            local_only=True,
            implemented=True,
        ),
        OpenBankingProvider(
            code="belvo",
            name="Belvo",
            countries=("CO", "MX", "BR"),
            capabilities=("accounts", "balances", "transactions", "webhooks"),
            required_environment=("OPEN_BANKING_BELVO_CLIENT_ID", "OPEN_BANKING_BELVO_CLIENT_SECRET", "OPEN_BANKING_BELVO_WEBHOOK_AUTHORIZATION", "SECURITY_ENCRYPTION_KEYS_JSON"),
            certification_prefix="OPEN_BANKING_BELVO",
            implemented=True,
        ),
        OpenBankingProvider(
            code="salt_edge",
            name="Salt Edge",
            countries=("CO",),
            capabilities=("accounts", "balances", "transactions", "webhooks"),
            required_environment=("OPEN_BANKING_SALT_EDGE_APP_ID", "OPEN_BANKING_SALT_EDGE_SECRET", "OPEN_BANKING_SALT_EDGE_CALLBACK_PUBLIC_KEY", "SECURITY_ENCRYPTION_KEYS_JSON"),
            certification_prefix="OPEN_BANKING_SALT_EDGE",
            implemented=True,
        ),
    )
}


def get_provider(code: str) -> OpenBankingProvider | None:
    return PROVIDERS.get((code or "").strip().lower())


def list_providers() -> list[dict]:
    return [provider.public_payload() for provider in PROVIDERS.values()]
