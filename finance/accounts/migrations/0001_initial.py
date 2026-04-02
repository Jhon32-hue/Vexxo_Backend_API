import django.db.models.deletion
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("cash", "Efectivo"),
                            ("bank", "Cuenta Bancaria"),
                            ("credit", "Tarjeta de Credito"),
                            ("wallet", "Monedero Digital"),
                            ("investment", "Cuenta de Inversion"),
                            ("savings", "Cuenta de Ahorros"),
                            ("loan", "Prestamo / Credito"),
                            ("brokerage", "Broker / Trading"),
                            ("retirement", "Retiro / Pension"),
                            ("crypto", "Cripto"),
                            ("prepaid", "Cuenta Prepago"),
                            ("joint", "Cuenta Compartida"),
                            ("custodial", "Cuenta Custodia"),
                            ("other", "Otro"),
                        ],
                        default="bank",
                        max_length=20,
                    ),
                ),
                (
                    "currency",
                    models.CharField(
                        choices=[
                            ("COP", "Peso Colombiano"),
                            ("MXN", "Peso Mexicano"),
                            ("ARS", "Peso Argentino"),
                            ("CLP", "Peso Chileno"),
                            ("PEN", "Sol Peruano"),
                            ("BRL", "Real Brasileno"),
                            ("PYG", "Guarani Paraguayo"),
                            ("UYU", "Peso Uruguayo"),
                            ("BOB", "Boliviano"),
                            ("CRC", "Colon Costarricense"),
                            ("GTQ", "Quetzal Guatemalteco"),
                            ("DOP", "Peso Dominicano"),
                            ("HNL", "Lempira Hondurena"),
                            ("NIO", "Cordoba Nicaraguense"),
                            ("PAB", "Balboa Panameno"),
                            ("USD", "Dolar Americano"),
                            ("EUR", "Euro"),
                            ("GBP", "Libra Esterlina"),
                            ("CHF", "Franco Suizo"),
                            ("CAD", "Dolar Canadiense"),
                            ("AUD", "Dolar Australiano"),
                            ("NZD", "Dolar Neozelandes"),
                            ("JPY", "Yen Japones"),
                            ("CNY", "Yuan Chino"),
                            ("INR", "Rupia India"),
                            ("KRW", "Won Surcoreano"),
                            ("SGD", "Dolar de Singapur"),
                            ("HKD", "Dolar de Hong Kong"),
                            ("AED", "Dirham de EAU"),
                            ("SAR", "Riyal Saudi"),
                        ],
                        default="COP",
                        max_length=10,
                    ),
                ),
                (
                    "country",
                    models.CharField(
                        blank=True,
                        help_text="Pais de la cuenta (ISO 3166-1 alpha-2, ej. CO, MX, AR).",
                        max_length=2,
                    ),
                ),
                (
                    "institution",
                    models.CharField(
                        blank=True,
                        help_text="Banco, billetera o institucion financiera asociada que administra la cuenta.",
                        max_length=120,
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Proveedor externo: banco, exchange, agregador de Open Finance, etc.",
                        max_length=64,
                    ),
                ),
                (
                    "external_id",
                    models.CharField(
                        blank=True,
                        help_text="ID externo de la cuenta en el proveedor (Open Finance, API externas, etc.).",
                        max_length=255,
                    ),
                ),
                (
                    "last_sync_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Ultima sincronizacion con el proveedor externo.",
                        null=True,
                    ),
                ),
                (
                    "sync_status",
                    models.CharField(
                        choices=[
                            ("idle", "Sincronizacion inactiva"),
                            ("ok", "Sincronizacion correcta"),
                            ("error", "Error de sincronizacion"),
                        ],
                        default="idle",
                        help_text="Estado de la ultima sincronizacion con el proveedor externo.",
                        max_length=16,
                    ),
                ),
                (
                    "sync_error_message",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Mensaje de error de la ultima sincronizacion, si aplica.",
                        max_length=255,
                    ),
                ),
                (
                    "allow_auto_sync",
                    models.BooleanField(
                        default=True,
                        help_text="Permite sincronizaciones automaticas periodicas con el proveedor externo.",
                    ),
                ),
                (
                    "initial_balance",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Saldo inicial al crear la cuenta en Vexxo. Puede ser negativo para cuentas de credito o prestamo.",
                        max_digits=14,
                    ),
                ),
                (
                    "balance",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Saldo actual cacheado y mantenido incrementalmente desde el ledger.",
                        max_digits=14,
                    ),
                ),
                (
                    "base_currency",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("COP", "Peso Colombiano"),
                            ("MXN", "Peso Mexicano"),
                            ("ARS", "Peso Argentino"),
                            ("CLP", "Peso Chileno"),
                            ("PEN", "Sol Peruano"),
                            ("BRL", "Real Brasileno"),
                            ("PYG", "Guarani Paraguayo"),
                            ("UYU", "Peso Uruguayo"),
                            ("BOB", "Boliviano"),
                            ("CRC", "Colon Costarricense"),
                            ("GTQ", "Quetzal Guatemalteco"),
                            ("DOP", "Peso Dominicano"),
                            ("HNL", "Lempira Hondurena"),
                            ("NIO", "Cordoba Nicaraguense"),
                            ("PAB", "Balboa Panameno"),
                            ("USD", "Dolar Americano"),
                            ("EUR", "Euro"),
                            ("GBP", "Libra Esterlina"),
                            ("CHF", "Franco Suizo"),
                            ("CAD", "Dolar Canadiense"),
                            ("AUD", "Dolar Australiano"),
                            ("NZD", "Dolar Neozelandes"),
                            ("JPY", "Yen Japones"),
                            ("CNY", "Yuan Chino"),
                            ("INR", "Rupia India"),
                            ("KRW", "Won Surcoreano"),
                            ("SGD", "Dolar de Singapur"),
                            ("HKD", "Dolar de Hong Kong"),
                            ("AED", "Dirham de EAU"),
                            ("SAR", "Riyal Saudi"),
                        ],
                        default="",
                        help_text="Moneda base del usuario (para vistas consolidadas). Opcional.",
                        max_length=10,
                    ),
                ),
                (
                    "virtual_balance_base",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Saldo de la cuenta convertido a la moneda base del usuario.",
                        max_digits=14,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "is_primary",
                    models.BooleanField(
                        default=False,
                        help_text="Indica si es la cuenta principal del usuario para reportes.",
                    ),
                ),
                (
                    "closed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Fecha y hora de cierre contable de la cuenta.",
                        null=True,
                    ),
                ),
                (
                    "closed_reason",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Motivo de cierre de la cuenta (opcional).",
                        max_length=255,
                    ),
                ),
                (
                    "archived",
                    models.BooleanField(
                        default=False,
                        help_text="Si esta marcada, se oculta en la UI por defecto pero sigue viva contablemente.",
                    ),
                ),
                (
                    "read_only",
                    models.BooleanField(
                        default=False,
                        help_text="Si esta activa, la cuenta es de solo lectura para el usuario (ej. cuenta compartida).",
                    ),
                ),
                (
                    "monthly_expense_limit",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Limite mensual de gasto para generar alertas o bloqueos (opcional).",
                        max_digits=14,
                        null=True,
                    ),
                ),
                (
                    "lock_on_limit",
                    models.BooleanField(
                        default=False,
                        help_text="Si esta activo, bloquea transacciones cuando se supera el limite mensual.",
                    ),
                ),
                (
                    "risk_level",
                    models.CharField(
                        blank=True,
                        default="normal",
                        help_text="Nivel de riesgo de la cuenta: low / normal / high.",
                        max_length=16,
                    ),
                ),
                (
                    "require_2fa_for_movements",
                    models.BooleanField(
                        default=False,
                        help_text="Si esta activo, requiere 2FA para movimientos desde esta cuenta.",
                    ),
                ),
                (
                    "auto_round_savings_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Si esta activo, redondea gastos y envia la diferencia a ahorro (regla futura).",
                    ),
                ),
                (
                    "goal_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Objetivo financiero asociado a esta cuenta (ahorro/meta).",
                        max_digits=14,
                        null=True,
                    ),
                ),
                (
                    "goal_deadline",
                    models.DateField(
                        blank=True,
                        help_text="Fecha objetivo para alcanzar 'goal_amount'. Opcional.",
                        null=True,
                    ),
                ),
                (
                    "last_activity_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Ultima actividad relevante sobre la cuenta (transaccion, cambio, etc.).",
                        null=True,
                    ),
                ),
                (
                    "last_transaction_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Monto de la ultima transaccion registrada en esta cuenta.",
                        max_digits=14,
                    ),
                ),
                (
                    "last_transaction_type",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Tipo de la ultima transaccion (expense/income/transfer).",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "shared_from_user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Usuario que compartio esta cuenta (escenario de cuentas observadas).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shared_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Cuenta",
                "verbose_name_plural": "Cuentas",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AccountMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                            ("viewer", "Viewer"),
                        ],
                        default="member",
                        max_length=16,
                    ),
                ),
                (
                    "access_mode",
                    models.CharField(
                        choices=[("full", "Full"), ("watch_only", "Watch Only")],
                        default="full",
                        max_length=16,
                    ),
                ),
                ("can_post_transactions", models.BooleanField(default=True)),
                ("can_manage_members", models.BooleanField(default=False)),
                ("can_manage_account_settings", models.BooleanField(default=False)),
                ("can_view_analytics", models.BooleanField(default=True)),
                ("invitation_token", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="accounts.account",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invited_account_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="account_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Account membership",
                "verbose_name_plural": "Account memberships",
            },
        ),
        migrations.CreateModel(
            name="BalanceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("as_of", models.DateTimeField(db_index=True)),
                ("balance_cached", models.DecimalField(decimal_places=6, max_digits=18)),
                ("balance_recomputed", models.DecimalField(decimal_places=6, max_digits=18)),
                ("drift", models.DecimalField(decimal_places=6, default=Decimal("0.000000"), max_digits=18)),
                ("tx_count", models.PositiveIntegerField(default=0)),
                ("is_consistent", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="balance_snapshots",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "ordering": ["-as_of"],
            },
        ),
        migrations.CreateModel(
            name="DomainEventOutbox",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("aggregate_type", models.CharField(max_length=64)),
                ("aggregate_id", models.CharField(max_length=64)),
                ("event_type", models.CharField(max_length=128)),
                ("idempotency_key", models.CharField(max_length=128, unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("metadata", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["occurred_at"],
                "indexes": [
                    models.Index(fields=["published_at", "occurred_at"], name="accounts_do_publish_d9cd46_idx"),
                    models.Index(fields=["event_type", "occurred_at"], name="accounts_do_event_t_6ee2da_idx"),
                ],
            },
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(fields=["owner", "is_active"], name="accounts_ac_owner_i_8fab56_idx"),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(fields=["owner", "type"], name="accounts_ac_owner_i_e5c9aa_idx"),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(fields=["owner", "archived"], name="accounts_ac_owner_i_aa7e1a_idx"),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(fields=["owner", "is_primary"], name="accounts_ac_owner_i_5b6618_idx"),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(fields=["owner", "provider"], name="accounts_ac_owner_i_0ba6be_idx"),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                fields=("owner", "name", "currency"),
                name="unique_account_per_user_currency",
            ),
        ),
        migrations.AddIndex(
            model_name="accountmembership",
            index=models.Index(fields=["user", "is_active"], name="accounts_ac_user_id_492107_idx"),
        ),
        migrations.AddIndex(
            model_name="accountmembership",
            index=models.Index(fields=["account", "is_active"], name="accounts_ac_account_529f2b_idx"),
        ),
        migrations.AddIndex(
            model_name="accountmembership",
            index=models.Index(fields=["account", "role"], name="accounts_ac_account_2f9b8d_idx"),
        ),
        migrations.AddConstraint(
            model_name="accountmembership",
            constraint=models.UniqueConstraint(
                fields=("account", "user"),
                name="unique_account_membership_per_user",
            ),
        ),
        migrations.AddIndex(
            model_name="balancesnapshot",
            index=models.Index(fields=["account", "as_of"], name="accounts_ba_account_763651_idx"),
        ),
        migrations.AddIndex(
            model_name="balancesnapshot",
            index=models.Index(fields=["is_consistent", "as_of"], name="accounts_ba_is_cons_30b1c3_idx"),
        ),
    ]
