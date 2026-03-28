from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_accountmembership_accepted_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="account_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="account",
            name="confidence_score",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="Confianza del dato de 0 a 100.",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="data_origin",
            field=models.CharField(
                choices=[
                    ("manual", "Declarada manualmente"),
                    ("imported", "Importada"),
                    ("synced", "Sincronizada externamente"),
                    ("inferred", "Inferida"),
                ],
                db_index=True,
                default="manual",
                help_text="Origen principal del dato de la cuenta.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="last_consistent_snapshot_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="account",
            name="last_domain_event_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="account",
            name="last_drift_detected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="account",
            name="sensitivity_level",
            field=models.CharField(
                choices=[
                    ("normal", "Normal"),
                    ("sensitive", "Sensible"),
                    ("high", "Alta sensibilidad"),
                ],
                default="normal",
                help_text="Clasificacion de sensibilidad del dato para gobierno y acceso.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="source_priority",
            field=models.CharField(
                choices=[
                    ("user_declared", "Declaracion del usuario"),
                    ("provider", "Proveedor externo"),
                    ("system_inferred", "Inferencia del sistema"),
                ],
                default="user_declared",
                help_text="Prioridad de la fuente cuando hay conflicto entre dato manual y externo.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="verification_level",
            field=models.CharField(
                choices=[
                    ("self_declared", "Autodeclarada"),
                    ("externally_verified", "Verificada externamente"),
                    ("reconciled", "Reconciliada"),
                ],
                db_index=True,
                default="self_declared",
                help_text="Nivel de verificacion del dato financiero de esta cuenta.",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="AccountOwnerMetrics",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_accounts", models.PositiveIntegerField(default=0)),
                ("active_accounts", models.PositiveIntegerField(default=0)),
                ("primary_accounts", models.PositiveIntegerField(default=0)),
                ("shared_accounts", models.PositiveIntegerField(default=0)),
                ("observed_accounts", models.PositiveIntegerField(default=0)),
                ("external_accounts", models.PositiveIntegerField(default=0)),
                ("investment_accounts", models.PositiveIntegerField(default=0)),
                ("credit_accounts", models.PositiveIntegerField(default=0)),
                ("currencies_count", models.PositiveIntegerField(default=0)),
                ("total_cached_balance_in_base", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("last_reconciled_at", models.DateTimeField(blank=True, null=True)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="account_owner_metrics", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Account owner metrics",
                "verbose_name_plural": "Account owner metrics",
            },
        ),
        migrations.CreateModel(
            name="AccountProductSignal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("signal_code", models.CharField(max_length=64)),
                ("signal_value", models.JSONField(blank=True, default=dict)),
                ("confidence", models.PositiveSmallIntegerField(default=0)),
                ("source", models.CharField(default="accounts", max_length=32)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("generated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_product_signals", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Account product signal",
                "verbose_name_plural": "Account product signals",
            },
        ),
        migrations.CreateModel(
            name="AccountRiskSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("risk_input_version", models.CharField(default="accounts.risk.v1", max_length=32)),
                ("product_mix_score", models.PositiveSmallIntegerField(default=0)),
                ("portfolio_stability_score", models.PositiveSmallIntegerField(default=0)),
                ("sync_reliability_score", models.PositiveSmallIntegerField(default=0)),
                ("external_verification_score", models.PositiveSmallIntegerField(default=0)),
                ("ownership_complexity_score", models.PositiveSmallIntegerField(default=0)),
                ("liquidity_proxy_score", models.PositiveSmallIntegerField(default=0)),
                ("active_credit_accounts", models.PositiveIntegerField(default=0)),
                ("active_investment_accounts", models.PositiveIntegerField(default=0)),
                ("external_linked_accounts", models.PositiveIntegerField(default=0)),
                ("dependency_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("sync_success_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("volatile_exposure_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("is_credit_ready_candidate", models.BooleanField(default=False)),
                ("segment_label", models.CharField(default="starter_financiero", max_length=64)),
                ("supporting_factors", models.JSONField(blank=True, default=dict)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="account_risk_snapshot", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Account risk snapshot",
                "verbose_name_plural": "Account risk snapshots",
            },
        ),
        migrations.CreateModel(
            name="AccountTypeDistribution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("account_type", models.CharField(max_length=20)),
                ("accounts_count", models.PositiveIntegerField(default=0)),
                ("total_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("exposure_percentage", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_type_distributions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Account type distribution",
                "verbose_name_plural": "Account type distributions",
            },
        ),
        migrations.CreateModel(
            name="AccountPortfolioSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_version", models.CharField(default="accounts.portfolio.v1", max_length=32)),
                ("total_accounts", models.PositiveIntegerField(default=0)),
                ("active_accounts", models.PositiveIntegerField(default=0)),
                ("primary_accounts", models.PositiveIntegerField(default=0)),
                ("shared_accounts", models.PositiveIntegerField(default=0)),
                ("observed_accounts", models.PositiveIntegerField(default=0)),
                ("external_accounts", models.PositiveIntegerField(default=0)),
                ("investment_accounts", models.PositiveIntegerField(default=0)),
                ("credit_accounts", models.PositiveIntegerField(default=0)),
                ("frozen_accounts", models.PositiveIntegerField(default=0)),
                ("archived_accounts", models.PositiveIntegerField(default=0)),
                ("closed_accounts", models.PositiveIntegerField(default=0)),
                ("idle_accounts", models.PositiveIntegerField(default=0)),
                ("currencies_count", models.PositiveIntegerField(default=0)),
                ("total_cached_balance_in_base", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("counts_by_type", models.JSONField(blank=True, default=dict)),
                ("counts_by_currency", models.JSONField(blank=True, default=dict)),
                ("balances_by_currency", models.JSONField(blank=True, default=dict)),
                ("ownership_distribution", models.JSONField(blank=True, default=dict)),
                ("has_multi_currency_accounts", models.BooleanField(default=False)),
                ("has_external_linked_accounts", models.BooleanField(default=False)),
                ("has_investment_exposure", models.BooleanField(default=False)),
                ("has_credit_products", models.BooleanField(default=False)),
                ("has_shared_financial_behavior", models.BooleanField(default=False)),
                ("has_goal_oriented_accounts", models.BooleanField(default=False)),
                ("has_recurrent_sync_failures", models.BooleanField(default=False)),
                ("has_idle_accounts", models.BooleanField(default=False)),
                ("has_many_small_accounts", models.BooleanField(default=False)),
                ("has_single_dependency_account", models.BooleanField(default=False)),
                ("avg_account_age_days", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("idle_accounts_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("frozen_accounts_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("archived_accounts_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("closed_accounts_ratio", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("portfolio_complexity_score", models.PositiveSmallIntegerField(default=0)),
                ("account_diversification_score", models.PositiveSmallIntegerField(default=0)),
                ("last_reconciled_at", models.DateTimeField(blank=True, null=True)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="account_portfolio_snapshot", to=settings.AUTH_USER_MODEL)),
                ("primary_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="accounts.account")),
            ],
            options={
                "verbose_name": "Account portfolio snapshot",
                "verbose_name_plural": "Account portfolio snapshots",
            },
        ),
        migrations.CreateModel(
            name="AccountCurrencyExposure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(max_length=10)),
                ("accounts_count", models.PositiveIntegerField(default=0)),
                ("estimated_total_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("exposure_percentage", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=6)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_currency_exposures", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Account currency exposure",
                "verbose_name_plural": "Account currency exposures",
            },
        ),
        migrations.AddConstraint(
            model_name="accountproductsignal",
            constraint=models.UniqueConstraint(fields=("owner", "signal_code"), name="unique_account_product_signal_per_owner"),
        ),
        migrations.AddConstraint(
            model_name="accounttypedistribution",
            constraint=models.UniqueConstraint(fields=("owner", "account_type"), name="unique_account_type_distribution_per_owner"),
        ),
        migrations.AddConstraint(
            model_name="accountcurrencyexposure",
            constraint=models.UniqueConstraint(fields=("owner", "currency"), name="unique_account_currency_exposure_per_owner"),
        ),
        migrations.AddIndex(
            model_name="accountproductsignal",
            index=models.Index(fields=["owner", "is_active"], name="accounts_acc_owner_i_3a17bc_idx"),
        ),
        migrations.AddIndex(
            model_name="accountproductsignal",
            index=models.Index(fields=["signal_code", "is_active"], name="accounts_acc_signal__77c347_idx"),
        ),
        migrations.AddIndex(
            model_name="accountcurrencyexposure",
            index=models.Index(fields=["owner", "currency"], name="accounts_acc_owner_i_2c905c_idx"),
        ),
        migrations.AddIndex(
            model_name="accounttypedistribution",
            index=models.Index(fields=["owner", "account_type"], name="accounts_acc_owner_i_4024ca_idx"),
        ),
    ]
