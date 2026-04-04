from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


_transaction_actor_id: ContextVar[str] = ContextVar("transaction_actor_id", default="")


def get_current_transaction_actor_id() -> str:
    return str(_transaction_actor_id.get("") or "")


@contextmanager
def bind_transaction_actor(actor=None):
    actor_id = str(getattr(actor, "id", "") or "")
    token = _transaction_actor_id.set(actor_id)
    try:
        yield actor_id
    finally:
        _transaction_actor_id.reset(token)
