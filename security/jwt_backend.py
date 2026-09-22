from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

import jwt
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenBackendExpiredToken


class MultiKeyTokenBackend(TokenBackend):
    """SimpleJWT backend that emits a key id and verifies retained keys."""

    def __init__(
        self,
        *,
        algorithm: str,
        active_version: str,
        signing_keys: dict[str, str],
        audience: str | Iterable[str] | None = None,
        issuer: str | None = None,
        leeway: float | int | timedelta | None = None,
        json_encoder=None,
    ) -> None:
        if not active_version or active_version not in signing_keys:
            raise TokenBackendError("JWT active key version is not present in the keyring.")
        self.active_version = active_version
        self.signing_keys = dict(signing_keys)
        super().__init__(
            algorithm=algorithm,
            signing_key=self.signing_keys[active_version],
            audience=audience,
            issuer=issuer,
            leeway=leeway,
            json_encoder=json_encoder,
        )

    def encode(self, payload: dict) -> str:
        jwt_payload = payload.copy()
        if self.audience is not None:
            jwt_payload["aud"] = self.audience
        if self.issuer is not None:
            jwt_payload["iss"] = self.issuer
        encoded = jwt.encode(
            jwt_payload,
            self.signing_keys[self.active_version],
            algorithm=self.algorithm,
            headers={"kid": self.active_version},
            json_encoder=self.json_encoder,
        )
        return encoded.decode("utf-8") if isinstance(encoded, bytes) else encoded

    def decode(self, token, verify: bool = True) -> dict:
        if not verify:
            return super().decode(token, verify=False)
        try:
            key_id = str(jwt.get_unverified_header(token).get("kid") or "")
        except jwt.InvalidTokenError as exc:
            raise TokenBackendError("Token header is invalid.") from exc

        candidates = (
            [(key_id, self.signing_keys[key_id])]
            if key_id and key_id in self.signing_keys
            else list(self.signing_keys.items()) if not key_id else []
        )
        if not candidates:
            raise TokenBackendError("Token key id is not accepted.")

        expired_error = None
        for _version, key in candidates:
            backend = TokenBackend(
                algorithm=self.algorithm,
                signing_key=key,
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway,
                json_encoder=self.json_encoder,
            )
            try:
                return backend.decode(token, verify=True)
            except TokenBackendExpiredToken as exc:
                expired_error = exc
            except TokenBackendError:
                continue
        if expired_error is not None:
            raise expired_error
        raise TokenBackendError("Token signature is invalid for the configured keyring.")


def build_jwt_token_backend(settings_dict: dict) -> MultiKeyTokenBackend:
    return MultiKeyTokenBackend(
        algorithm=settings_dict["ALGORITHM"],
        active_version=settings_dict["ACTIVE_KEY_VERSION"],
        signing_keys=settings_dict["SIGNING_KEYS"],
        audience=settings_dict.get("AUDIENCE"),
        issuer=settings_dict.get("ISSUER"),
        leeway=settings_dict.get("LEEWAY", 0),
        json_encoder=settings_dict.get("JSON_ENCODER"),
    )
