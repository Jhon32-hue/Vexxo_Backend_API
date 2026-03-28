"""
Signals de lifecycle del usuario.

Descripcion general:
- detecta altas y cambios relevantes del modelo `User`
- publica eventos de dominio despues de commit para desacoplar onboarding,
  cuentas, alertas y otras reacciones del sistema

Analisis detallado:
- `identity.users` es el origen del lifecycle del usuario, pero no debe crear
  directamente recursos de otros bounded contexts
- este archivo captura estado previo del usuario, detecta cambios semanticos y
  los traduce a eventos versionados
- otros modulos como `finance.accounts` o listeners internos de identidad ya
  reaccionan sobre esos eventos usando el bus de dominio
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from common.domain_events import EventPriority
from identity.users.domain import UserDomainEventTypes, build_user_lifecycle_payload
from identity.users.models import UserStatus
from identity.users.services.event_service import publish_user_event_after_commit

User = get_user_model()


@dataclass
class PreviousUserState:
    plan: str
    status: str
    preferred_currency: str
    onboarding_completed: bool
    is_verified: bool
    is_active: bool
    first_name: str
    last_name: str
    phone_number: str
    locale: str
    timezone_name: str


def _capture_previous_state(instance) -> PreviousUserState | None:
    if not instance.pk:
        return None
    previous = User.objects.filter(pk=instance.pk).first()
    if previous is None:
        return None
    return PreviousUserState(
        plan=previous.plan,
        status=previous.status,
        preferred_currency=previous.preferred_currency,
        onboarding_completed=bool(previous.onboarding_completed),
        is_verified=bool(previous.is_verified),
        is_active=bool(previous.is_active),
        first_name=previous.first_name,
        last_name=previous.last_name,
        phone_number=previous.phone_number or "",
        locale=previous.locale,
        timezone_name=previous.timezone_name,
    )


def _state_to_dict(state: PreviousUserState | None) -> dict:
    if state is None:
        return {}
    return {
        "plan": state.plan,
        "status": state.status,
        "preferred_currency": state.preferred_currency,
        "onboarding_completed": state.onboarding_completed,
        "is_verified": state.is_verified,
        "is_active": state.is_active,
        "first_name": state.first_name,
        "last_name": state.last_name,
        "phone_number": state.phone_number,
        "locale": state.locale,
        "timezone_name": state.timezone_name,
    }


@receiver(pre_save, sender=User)
def capture_user_previous_state(sender, instance, **kwargs):
    instance._previous_user_state = _capture_previous_state(instance)


@receiver(post_save, sender=User)
def emit_user_lifecycle_events(sender, instance, created: bool, **kwargs):
    previous = getattr(instance, "_previous_user_state", None)
    before = _state_to_dict(previous)

    if created:
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_REGISTERED,
            payload=build_user_lifecycle_payload(
                user=instance,
                change="registered",
                extra={"registration_channel": "email_password"},
            ),
            metadata={"source": "users.signals"},
            priority=EventPriority.HIGH,
        )
        if instance.is_verified:
            publish_user_event_after_commit(
                event_type=UserDomainEventTypes.USER_VERIFIED,
                payload=build_user_lifecycle_payload(user=instance, change="verified"),
                metadata={"source": "users.signals"},
                priority=EventPriority.NORMAL,
            )
        return

    if previous is None:
        return

    profile_changed = any(
        [
            previous.first_name != instance.first_name,
            previous.last_name != instance.last_name,
            previous.phone_number != (instance.phone_number or ""),
            previous.locale != instance.locale,
            previous.timezone_name != instance.timezone_name,
        ]
    )
    if profile_changed:
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_PROFILE_UPDATED,
            payload=build_user_lifecycle_payload(
                user=instance,
                change="profile_updated",
                before=before,
                after={
                    "first_name": instance.first_name,
                    "last_name": instance.last_name,
                    "phone_number": instance.phone_number or "",
                    "locale": instance.locale,
                    "timezone_name": instance.timezone_name,
                },
            ),
            metadata={"source": "users.signals"},
        )

    if previous.plan != instance.plan:
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_PLAN_CHANGED,
            payload=build_user_lifecycle_payload(
                user=instance,
                change="plan_changed",
                before={"plan": previous.plan},
                after={"plan": instance.plan},
            ),
            metadata={"source": "users.signals"},
            priority=EventPriority.HIGH,
        )

    if previous.preferred_currency != instance.preferred_currency:
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_CURRENCY_CHANGED,
            payload=build_user_lifecycle_payload(
                user=instance,
                change="preferred_currency_changed",
                before={"preferred_currency": previous.preferred_currency},
                after={"preferred_currency": instance.preferred_currency},
            ),
            metadata={"source": "users.signals"},
            priority=EventPriority.HIGH,
        )

    if not previous.onboarding_completed and instance.onboarding_completed:
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_ONBOARDING_COMPLETED,
            payload=build_user_lifecycle_payload(user=instance, change="onboarding_completed"),
            metadata={"source": "users.signals"},
        )

    if not previous.is_verified and instance.is_verified:
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_VERIFIED,
            payload=build_user_lifecycle_payload(user=instance, change="verified"),
            metadata={"source": "users.signals"},
        )

    if (
        (previous.status != UserStatus.SUSPENDED and instance.status == UserStatus.SUSPENDED)
        or (previous.is_active and not instance.is_active)
    ):
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_SUSPENDED,
            payload=build_user_lifecycle_payload(
                user=instance,
                change="suspended",
                before=before,
                after={"status": instance.status, "is_active": instance.is_active},
            ),
            metadata={"source": "users.signals"},
            priority=EventPriority.HIGH,
        )

    if (
        (previous.status != UserStatus.ACTIVE and instance.status == UserStatus.ACTIVE)
        or (not previous.is_active and instance.is_active)
    ):
        publish_user_event_after_commit(
            event_type=UserDomainEventTypes.USER_ACTIVATED,
            payload=build_user_lifecycle_payload(
                user=instance,
                change="activated",
                before=before,
                after={"status": instance.status, "is_active": instance.is_active},
            ),
            metadata={"source": "users.signals"},
            priority=EventPriority.HIGH,
        )
