from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings

from integrations.open_banking.local_mock import list_local_mock_accounts
from integrations.open_banking.contracts import (
    ProviderPage,
    ReconciliationSnapshot,
    normalize_account,
    normalize_transaction,
    reconciliation_snapshot,
)


class OpenBankingProviderError(ValueError):
    def __init__(self, message: str, *, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuthorizationSession:
    authorization_url: str = ""
    widget_access_token: str = ""
    external_customer_id: str = ""


class BaseOpenBankingAdapter:
    code = ""

    def begin_authorization(self, *, connection) -> AuthorizationSession:
        raise OpenBankingProviderError("Adapter no implementado.", code="adapter_unavailable")

    def fetch_accounts_page(self, *, connection, cursor: str = "") -> ProviderPage:
        raise OpenBankingProviderError("Adapter no implementado.", code="adapter_unavailable")

    def list_accounts(self, *, connection) -> list[dict]:
        results: list[dict] = []
        cursor = ""
        for _ in range(100):
            page = self.fetch_accounts_page(connection=connection, cursor=cursor)
            results.extend(self.normalize_account(row, connection=connection) for row in page.items)
            if not page.has_more or not page.next_cursor:
                break
            cursor = page.next_cursor
        return [row for row in results if row.get("external_account_id")]

    def request_sync(self, *, connection) -> None:
        raise OpenBankingProviderError("Adapter no implementado.", code="adapter_unavailable")

    def fetch_transactions_page(self, *, connection, external_account_id: str, cursor: str = "") -> ProviderPage:
        raise OpenBankingProviderError("Adapter no implementado.", code="adapter_unavailable")

    def normalize_account(self, row: dict, *, connection) -> dict:
        return normalize_account(self.code, row, institution_name=connection.institution_name)

    def normalize_transaction(self, row: dict) -> dict:
        return normalize_transaction(self.code, row)

    def list_transactions(self, *, connection, external_account_id: str) -> list[dict]:
        results: list[dict] = []
        cursor = ""
        for _ in range(100):
            page = self.fetch_transactions_page(
                connection=connection,
                external_account_id=external_account_id,
                cursor=cursor,
            )
            results.extend(self.normalize_transaction(row) for row in page.items)
            if not page.has_more or not page.next_cursor:
                break
            cursor = page.next_cursor
        return [row for row in results if row.get("external_id") and row.get("date")]

    def refresh_credentials(self, *, connection) -> None:
        self.request_sync(connection=connection)

    def reconcile(self, *, connection, external_account_id: str) -> ReconciliationSnapshot:
        account = next(
            (row for row in self.list_accounts(connection=connection) if row["external_account_id"] == external_account_id),
            None,
        )
        if account is None:
            raise OpenBankingProviderError("El proveedor no reporto la cuenta para reconciliacion.", code="account_not_found")
        return reconciliation_snapshot(self.code, account)

    def revoke(self, *, connection) -> None:
        raise OpenBankingProviderError("Adapter no implementado.", code="adapter_unavailable")


class LocalMockOpenBankingAdapter(BaseOpenBankingAdapter):
    code = "local_mock"

    def begin_authorization(self, *, connection) -> AuthorizationSession:
        return AuthorizationSession()

    def fetch_accounts_page(self, *, connection, cursor: str = "") -> ProviderPage:
        return ProviderPage(items=list_local_mock_accounts(connection=connection))

    def request_sync(self, *, connection) -> None:
        return None

    def fetch_transactions_page(self, *, connection, external_account_id: str, cursor: str = "") -> ProviderPage:
        return ProviderPage(items=[])

    def refresh_credentials(self, *, connection) -> None:
        return None

    def reconcile(self, *, connection, external_account_id: str) -> ReconciliationSnapshot:
        link = connection.account_links.select_related("account").filter(external_account_id=external_account_id).first()
        if link is None:
            raise OpenBankingProviderError("Cuenta local no encontrada.", code="account_not_found")
        return ReconciliationSnapshot(
            external_account_id=external_account_id,
            currency=link.account.currency,
            current_balance=link.account.balance,
            available_balance=link.account.balance,
            as_of=None,
            provider=self.code,
        )

    def revoke(self, *, connection) -> None:
        return None


class BelvoOpenBankingAdapter(BaseOpenBankingAdapter):
    code = "belvo"

    def __init__(self):
        self.base_url = str(getattr(settings, "OPEN_BANKING_BELVO_BASE_URL", "") or "").rstrip("/")
        self.client_id = str(getattr(settings, "OPEN_BANKING_BELVO_CLIENT_ID", "") or "")
        self.client_secret = str(getattr(settings, "OPEN_BANKING_BELVO_CLIENT_SECRET", "") or "")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        if not self.base_url or not self.client_id or not self.client_secret:
            raise OpenBankingProviderError("Belvo no esta configurado.", code="provider_not_configured")
        try:
            response = requests.request(method, f"{self.base_url}{path}", auth=(self.client_id, self.client_secret), timeout=15, **kwargs)
            payload = response.json() if response.content else {}
        except (requests.RequestException, ValueError) as exc:
            raise OpenBankingProviderError("Belvo no respondio correctamente.", code="transport_error") from exc
        if not response.ok:
            raise OpenBankingProviderError("Belvo rechazo la solicitud.", code=f"belvo_http_{response.status_code}")
        return payload

    def begin_authorization(self, *, connection) -> AuthorizationSession:
        payload = self._request("POST", "/api/token/", json={
            "id": self.client_id,
            "password": self.client_secret,
            "scopes": "read_institutions,write_links,read_links,read_accounts,read_transactions",
            "fetch_resources": ["ACCOUNTS", "TRANSACTIONS"],
            "external_id": str(connection.public_id),
        })
        token = str(payload.get("access") or payload.get("token") or "")
        if not token:
            raise OpenBankingProviderError("Belvo no devolvio widget token.", code="invalid_widget_response")
        return AuthorizationSession(widget_access_token=token)

    def fetch_accounts_page(self, *, connection, cursor: str = "") -> ProviderPage:
        if not connection.external_connection_id:
            return ProviderPage(items=[])
        params = {"link": connection.external_connection_id, "page_size": 100}
        if cursor:
            params["page"] = cursor
        payload = self._request("GET", "/api/accounts/", params=params)
        next_cursor = _belvo_next_cursor(payload.get("next"))
        return ProviderPage(items=list(payload.get("results") or []), next_cursor=next_cursor, has_more=bool(next_cursor))

    def request_sync(self, *, connection) -> None:
        if not connection.external_connection_id:
            raise OpenBankingProviderError("La conexion Belvo aun no tiene link_id.", code="authorization_pending")
        self._request("POST", "/api/transactions/", json={"link": connection.external_connection_id})

    def fetch_transactions_page(self, *, connection, external_account_id: str, cursor: str = "") -> ProviderPage:
        params = {
            "link": connection.external_connection_id,
            "account": external_account_id,
            "page_size": 250,
        }
        if cursor:
            params["page"] = cursor
        payload = self._request("GET", "/api/transactions/", params=params)
        next_cursor = _belvo_next_cursor(payload.get("next"))
        return ProviderPage(items=list(payload.get("results") or []), next_cursor=next_cursor, has_more=bool(next_cursor))

    def revoke(self, *, connection) -> None:
        if connection.external_connection_id:
            self._request("DELETE", f"/api/links/{connection.external_connection_id}/")


class SaltEdgeOpenBankingAdapter(BaseOpenBankingAdapter):
    code = "salt_edge"

    def __init__(self):
        self.base_url = str(getattr(settings, "OPEN_BANKING_SALT_EDGE_BASE_URL", "") or "").rstrip("/")
        self.app_id = str(getattr(settings, "OPEN_BANKING_SALT_EDGE_APP_ID", "") or "")
        self.secret = str(getattr(settings, "OPEN_BANKING_SALT_EDGE_SECRET", "") or "")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        if not self.base_url or not self.app_id or not self.secret:
            raise OpenBankingProviderError("Salt Edge no esta configurado.", code="provider_not_configured")
        headers = {"Accept": "application/json", "Content-Type": "application/json", "App-id": self.app_id, "Secret": self.secret}
        try:
            response = requests.request(method, f"{self.base_url}{path}", headers=headers, timeout=15, **kwargs)
            payload = response.json() if response.content else {}
        except (requests.RequestException, ValueError) as exc:
            raise OpenBankingProviderError("Salt Edge no respondio correctamente.", code="transport_error") from exc
        if not response.ok:
            raise OpenBankingProviderError("Salt Edge rechazo la solicitud.", code=f"salt_edge_http_{response.status_code}")
        return payload

    def _customer_id(self, connection) -> str:
        existing = connection.owner.open_banking_connections.filter(provider=self.code).exclude(pk=connection.pk).order_by("-created_at").first()
        customer_id = str(((existing.safe_metadata if existing else {}) or {}).get("external_customer_id") or "")
        if customer_id:
            return customer_id
        payload = self._request("POST", "/customers", json={"data": {"identifier": f"vexxo-{connection.owner_id}"}})
        customer_id = str((payload.get("data") or {}).get("customer_id") or "")
        if not customer_id:
            raise OpenBankingProviderError("Salt Edge no devolvio customer_id.", code="invalid_customer_response")
        return customer_id

    def begin_authorization(self, *, connection) -> AuthorizationSession:
        customer_id = self._customer_id(connection)
        return_to = str(getattr(settings, "OPEN_BANKING_SALT_EDGE_RETURN_URL", "") or "")
        data: dict[str, Any] = {
            "customer_id": customer_id,
            "consent": {"scopes": list(connection.scopes), "period_days": 90},
            "attempt": {"fetch_scopes": ["accounts", "balance", "transactions"]},
            "custom_fields": {"vexxo_connection_id": str(connection.public_id)},
        }
        if return_to:
            data["return_to"] = return_to
        payload = self._request("POST", "/connections/connect", json={"data": data})
        connect_url = str((payload.get("data") or {}).get("connect_url") or "")
        if not connect_url:
            raise OpenBankingProviderError("Salt Edge no devolvio connect_url.", code="invalid_widget_response")
        return AuthorizationSession(authorization_url=connect_url, external_customer_id=customer_id)

    def fetch_accounts_page(self, *, connection, cursor: str = "") -> ProviderPage:
        if not connection.external_connection_id:
            return ProviderPage(items=[])
        params = {"connection_id": connection.external_connection_id, "per_page": 100}
        if cursor:
            params["from_id"] = cursor
        payload = self._request("GET", "/accounts", params=params)
        next_cursor = str((payload.get("meta") or {}).get("next_id") or "")
        return ProviderPage(items=list(payload.get("data") or []), next_cursor=next_cursor, has_more=bool(next_cursor))

    def request_sync(self, *, connection) -> None:
        if not connection.external_connection_id:
            raise OpenBankingProviderError("La conexion Salt Edge aun no tiene connection_id.", code="authorization_pending")
        self._request("PUT", f"/connections/{connection.external_connection_id}/refresh", json={"data": {}})

    def fetch_transactions_page(self, *, connection, external_account_id: str, cursor: str = "") -> ProviderPage:
        params = {
            "connection_id": connection.external_connection_id,
            "account_id": external_account_id,
            "pending": "true",
            "duplicated": "false",
            "per_page": 250,
        }
        if cursor:
            params["from_id"] = cursor
        payload = self._request("GET", "/transactions", params=params)
        next_cursor = str((payload.get("meta") or {}).get("next_id") or "")
        return ProviderPage(items=list(payload.get("data") or []), next_cursor=next_cursor, has_more=bool(next_cursor))

    def revoke(self, *, connection) -> None:
        if connection.external_connection_id:
            self._request("DELETE", f"/connections/{connection.external_connection_id}")


ADAPTERS = {"local_mock": LocalMockOpenBankingAdapter, "belvo": BelvoOpenBankingAdapter, "salt_edge": SaltEdgeOpenBankingAdapter}


def _belvo_next_cursor(next_url: str | None) -> str:
    if not next_url:
        return ""
    return str((parse_qs(urlparse(str(next_url)).query).get("page") or [""])[0])


def get_open_banking_adapter(provider: str) -> BaseOpenBankingAdapter:
    adapter = ADAPTERS.get(str(provider or "").strip().lower())
    if adapter is None:
        raise OpenBankingProviderError("Proveedor no soportado.", code="unsupported_provider")
    return adapter()
