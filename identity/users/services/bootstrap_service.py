"""
Bootstrap funcional del usuario dentro del bounded context de identidad.

Descripcion general:
- crea defaults del usuario que no pertenecen a `accounts`
- encapsula categorias base, equipo personal y alertas de bienvenida

Analisis detallado:
- el usuario registrado ya no debe crear todo directamente desde un signal
  acoplado; este servicio se invoca desde listeners de eventos para mantener el
  flujo desacoplado
- `accounts` se inicializa aparte porque es otro bounded context
"""

from __future__ import annotations

import logging

from alerts.alerts.models.alerts import Alert, AlertCategory, AlertSeverity, AlertStatus, AlertType
from finance.categories.models.categories import Category
from social.teams.models.membership import Membership
from social.teams.models.team import Team

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = (
    ("Alimentacion", "expense"),
    ("Transporte", "expense"),
    ("Salud", "expense"),
    ("Educacion", "expense"),
    ("Vivienda", "expense"),
    ("Servicios", "expense"),
    ("Entretenimiento", "expense"),
    ("Mascotas", "expense"),
    ("Donaciones", "expense"),
    ("Salario", "income"),
    ("Freelance", "income"),
    ("Inversiones", "income"),
    ("Ahorro", "income"),
    ("Otros ingresos", "income"),
)


def ensure_default_categories(user) -> int:
    created_total = 0
    for name, type_ in DEFAULT_CATEGORIES:
        _, created = Category.objects.get_or_create(
            owner=user,
            name=name,
            defaults={"type": type_},
        )
        created_total += int(created)
    return created_total


def ensure_personal_team(user) -> Team:
    team, _ = Team.objects.get_or_create(
        owner=user,
        name=f"Equipo personal de {user.display_name}",
        defaults={
            "description": "Equipo personal inicial del usuario.",
            "is_personal": True,
        },
    )
    Membership.objects.get_or_create(
        team=team,
        user=user,
        defaults={"role": "owner", "is_active": True},
    )
    return team


def ensure_welcome_alerts(user) -> int:
    created_total = 0
    if not Alert.objects.filter(owner=user, type=AlertType.SYSTEM, title="Bienvenido a Vexxo").exists():
        Alert.objects.create(
            owner=user,
            type=AlertType.SYSTEM,
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.INFO,
            status=AlertStatus.NEW,
            title="Bienvenido a Vexxo",
            message=(
                f"Hola {user.display_name}. Tu espacio base ya esta listo para empezar "
                "a organizar tu vida financiera."
            ),
            payload={
                "actions": [
                    {"label": "Completar onboarding", "url": "/onboarding"},
                    {"label": "Crear primera cuenta", "url": "/cuentas/nueva"},
                ]
            },
            source="users.bootstrap",
        )
        created_total += 1

    if not Alert.objects.filter(owner=user, type=AlertType.SYSTEM, title="Siguiente paso recomendado").exists():
        Alert.objects.create(
            owner=user,
            type=AlertType.SYSTEM,
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.INFO,
            status=AlertStatus.NEW,
            title="Siguiente paso recomendado",
            message=(
                "Define tus cuentas principales y registra tus primeras transacciones "
                "para activar recomendaciones y alertas inteligentes."
            ),
            payload={},
            source="users.bootstrap",
        )
        created_total += 1
    return created_total


def bootstrap_registered_user(user) -> dict:
    categories_created = ensure_default_categories(user)
    team = ensure_personal_team(user)
    alerts_created = ensure_welcome_alerts(user)

    logger.info(
        "[users.bootstrap] owner=%s categories_created=%s alerts_created=%s team_id=%s",
        user.pk,
        categories_created,
        alerts_created,
        getattr(team, "pk", None),
    )
    return {
        "categories_created": categories_created,
        "alerts_created": alerts_created,
        "team_id": str(team.pk),
    }
