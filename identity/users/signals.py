# users/signals.py
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from finance.accounts.models.account import Account
from finance.categories.models.categories import Category
from alerts.alerts.models import Alert
from social.teams.models import Team, Membership

User = get_user_model()
logger = logging.getLogger(__name__)

# --------- CONFIGURACIÓN BASE --------- #

DEFAULT_ACCOUNTS = (
    ("Efectivo principal", "COP", 0),
    ("Tarjeta de crédito", "COP", 0),
    ("Ahorros", "COP", 0),
    ("Inversiones", "USD", 0),
)

DEFAULT_CATEGORIES = (
    ("Alimentación", "expense"),
    ("Transporte", "expense"),
    ("Salud", "expense"),
    ("Educación", "expense"),
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

# --------- HELPERS --------- #


def setup_default_accounts(user):
    currency = user.preferred_currency or "COP"

    for name, cur, bal in DEFAULT_ACCOUNTS:
        acc, created = Account.objects.get_or_create(
            owner=user,
            name=name,
            defaults={"currency": cur or currency, "balance": bal},
        )
        if created:
            logger.debug(
                f"[INIT:ACCOUNTS] Cuenta creada: {name} para {user.username}"
            )

    # Bono inicial
    bonus, created_bonus = Account.objects.get_or_create(
        owner=user,
        name="Gratificación de bienvenida",
        defaults={"currency": currency, "balance": 50000},
    )
    if created_bonus:
        logger.info(
            f"[INIT:BONUS] Bono creado para {user.username} con saldo {bonus.balance}"
        )


def setup_default_categories(user):
    for name, type_ in DEFAULT_CATEGORIES:
        _, created = Category.objects.get_or_create(
            owner=user,
            name=name,
            defaults={"type": type_},
        )
        if created:
            logger.debug(
                f"[INIT:CATEGORIES] Categoría '{name}' creada para {user.username}"
            )


def setup_personal_team(user):
    team, created = Team.objects.get_or_create(
        name=f"Equipo de {user.username}",
        defaults={},
    )

    Membership.objects.get_or_create(
        user=user,
        team=team,
        defaults={"role": "owner"},
    )

    if created:
        logger.info(f"[INIT:TEAMS] Equipo personal creado para {user.username}")


def setup_welcome_alerts(user):
    if Alert.objects.filter(owner=user, type="welcome").exists():
        return

    Alert.objects.create(
        owner=user,
        type="welcome",
        payload={
            "title": "¡Bienvenido a tu nueva plataforma financiera!",
            "message": (
                f"Hola {user.first_name or user.username}, ya tienes tu cuenta "
                "principal y categorías básicas listas para empezar."
            ),
            "actions": [
                {"label": "Conectar WhatsApp", "url": "/integraciones/whatsapp"}, #Registro de API  
                {"label": "Registrar tu primer gasto", "url": "/transacciones/nueva"},
            ],
        },
    )

    Alert.objects.create(
        owner=user,
        type="tip",
        payload={
            "title": "Consejo de inicio 💡",
            "message": (
                "Empieza registrando tus gastos del día. Con el tiempo podremos "
                "detectar patrones, alertas de sobregasto y ayudarte a cumplir tus metas."
            ),
        },
    )

    logger.debug(f"[INIT:ALERTS] Alertas creadas para {user.username}")


# --------- SEÑAL PRINCIPAL --------- #


@receiver(post_save, sender=User)
def initialize_user_environment(sender, instance, created: bool, **kwargs):
    """
    Inicializa cuentas, categorías, equipo personal y alertas
    cuando se crea un nuevo usuario.
    """
    if not created:
        return

    try:
        with transaction.atomic():
            setup_default_accounts(instance)
            setup_default_categories(instance)
            setup_personal_team(instance)
            setup_welcome_alerts(instance)

        logger.info(f"[INIT] Entorno inicial creado para {instance.username}")
    except Exception as e:
        logger.error(
            f"[INIT:ERROR] Fallo inicializando entorno para {instance.username}: {e}",
            exc_info=True,
        )
