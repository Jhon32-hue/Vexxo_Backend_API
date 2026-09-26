import hashlib
import json

from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from finance.transactions.Models.manual_receipt import ManualTransactionReceipt


class SubmissionConflict(APIException):
    status_code = 409
    default_detail = "Esta clave ya pertenece a otro movimiento. Revisa tu historial."


class SubmissionRemoved(APIException):
    status_code = 410
    default_detail = "El movimiento original fue eliminado; no se volvera a crear."


@transaction.atomic
def submit_manual_once(*, actor, key, payload, create):
    if len(key) > 160:
        raise ValidationError({"Idempotency-Key": "Maximo 160 caracteres."})
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    payload_hash = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest()
    # Serialize submissions for this actor, including the first receipt insert.
    type(actor).objects.select_for_update().get(pk=actor.pk)
    receipt = ManualTransactionReceipt.objects.filter(actor=actor, key_hash=key_hash).first()
    if receipt:
        if receipt.payload_hash != payload_hash:
            raise SubmissionConflict()
        if receipt.transaction_id is None:
            raise SubmissionRemoved()
        return receipt.transaction, True
    movement = create()
    ManualTransactionReceipt.objects.create(
        actor=actor, key_hash=key_hash, payload_hash=payload_hash, transaction=movement
    )
    return movement, False
