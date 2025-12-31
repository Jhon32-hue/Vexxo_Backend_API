from decimal import Decimal

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from accounts.models.account import Account, AccountType


class AccountSerializer(serializers.ModelSerializer):
    # Derivados / calculados
    current_balance = serializers.SerializerMethodField(read_only=True)
    total_transactions = serializers.IntegerField(read_only=True)
    is_closed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "owner",
            "name",
            "type",
            "currency",
            # Campos de integración (solo lectura para el cliente externo)
            "institution",
            "external_id",
            "last_sync_at",
            # Campos monetarios
            "initial_balance",
            "balance",
            "current_balance",
            # Derivados
            "total_transactions",
            # Estado
            "is_active",
            "is_primary",
            "is_closed",
            # Timestamps
            "created_at",
            "updated_at",
            "closed_at",
        ]
        read_only_fields = [
            "owner",
            "balance",
            "current_balance",
            "total_transactions",
            "is_closed",
            "last_sync_at",
            "institution",    # se manejarán en integraciones futuras
            "external_id",    # idem
            "created_at",
            "updated_at",
            "closed_at",
        ]

    # ========= HELPERS DE PLAN / LÍMITES =========

    def _get_user_plan(self, user) -> str:
        """
        Obtiene el plan del usuario. Si no hay settings o plan definido,
        asumimos 'free' por defecto.
        """
        settings = getattr(user, "settings", None)
        plan = getattr(settings, "plan", None)
        if plan in {"free", "plus", "pro"}:
            return plan
        return "free"

    def _get_plan_limits(self, plan: str) -> dict:
        """
        Devuelve los límites asociados a cada plan.
        Estos valores luego se pueden mover a un módulo de configuración
        o incluso a la base de datos en Users.
        """
        config = {
            "free": {
                "max_accounts": 3,
                "max_primary": 1,
                "max_investment_accounts": 1,
            },
            "plus": {
                "max_accounts": 6,
                "max_primary": 3,
                "max_investment_accounts": 3,
            },
            "pro": {
                "max_accounts": None,              # ilimitado
                "max_primary": None,              # ilimitado
                "max_investment_accounts": None,  # ilimitado
            },
        }
        return config.get(plan, config["free"])

    # ========= REPRESENTACIÓN =========

    def get_current_balance(self, obj):
        """
        Devolvemos el balance persistido.
        Si se requiere un cálculo en tiempo real, usar el método
        'current_balance()' del modelo. En este caso, puede ser costoso
        por las agregaciones sobre transacciones, así que aquí
        solo leemos el campo.
        """
        return obj.balance

    def to_representation(self, instance):
        """
        Optimización ligera: si el queryset viene anotado con
        total_transactions, lo usamos; si no, hacemos el count().
        """
        data = super().to_representation(instance)

        annotated_total = getattr(instance, "total_transactions", None)
        if annotated_total is not None:
            data["total_transactions"] = annotated_total
        else:
            data["total_transactions"] = instance.transactions_qs().count()

        data["is_closed"] = instance.is_closed
        return data

    # ========= VALIDACIONES POR CAMPO =========

    def validate_name(self, value):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return value

        qs = Account.objects.filter(owner=request.user, name=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                _("Ya existe una cuenta con este nombre para este usuario.")
            )
        return value

    def validate_initial_balance(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError(
                _("El saldo inicial no puede ser negativo.")
            )
        return value

    # ========= VALIDACIONES GLOBALES =========

    def validate(self, attrs):
        """
        Reglas de negocio avanzadas:

        1) Ledger-safe:
           - No permitir modificar initial_balance si ya existen transacciones.
           - No permitir cambiar la moneda si ya existen transacciones.
           - No permitir reabrir cuentas cerradas desde este serializer.
           - No permitir desactivar/cerrar una cuenta con saldo distinto de 0.

        2) Plan / suscripción:
           - Límite de cuentas activas por plan (free: 3, plus: 6, pro: ilimitado).
           - Límite de cuentas primarias por plan.
           - Límite de cuentas de inversión por plan.
        """
        instance = getattr(self, "instance", None)
        request = self.context.get("request")
        user = request.user if request else None

        # ---------- 1) Reglas ligadas al ledger ----------

        has_instance = instance is not None
        has_transactions = instance.transactions_qs().exists() if has_instance else False

        # 1.a) initial_balance inmutable si hay transacciones
        if has_instance and "initial_balance" in attrs and has_transactions:
            if attrs["initial_balance"] != instance.initial_balance:
                raise serializers.ValidationError(
                    {
                        "initial_balance": _(
                            "No puedes cambiar el saldo inicial cuando ya existen transacciones."
                        )
                    }
                )

        # 1.b) currency inmutable si hay transacciones
        if has_instance and "currency" in attrs and has_transactions:
            if attrs["currency"] != instance.currency:
                raise serializers.ValidationError(
                    {
                        "currency": _(
                            "No puedes cambiar la moneda de una cuenta que ya tiene transacciones."
                        )
                    }
                )

        # 1.c) no reabrir cuentas cerradas desde la API normal
        if has_instance and instance.is_closed and attrs.get("is_active") is True:
            raise serializers.ValidationError(
                {
                    "is_active": _(
                        "Esta cuenta está cerrada y no puede reabrirse desde esta operación."
                    )
                }
            )

        # 1.d) no desactivar/cerrar cuentas con saldo distinto de 0
        if has_instance and attrs.get("is_active") is False:
            if instance.balance != Decimal("0.00"):
                raise serializers.ValidationError(
                    {
                        "is_active": _(
                            "No puedes desactivar o cerrar una cuenta mientras tenga saldo distinto de cero."
                        )
                    }
                )

        # ---------- 2) Reglas ligadas al plan / suscripción ----------

        if user and not has_instance:
            # Solo aplican límites de creación cuando es una cuenta nueva
            plan = self._get_user_plan(user)
            limits = self._get_plan_limits(plan)

            # 2.a) límite de cuentas activas por plan
            max_accounts = limits.get("max_accounts")
            if max_accounts is not None:
                active_accounts = Account.objects.filter(
                    owner=user,
                    is_active=True,
                ).count()
                if active_accounts >= max_accounts:
                    raise serializers.ValidationError(
                        {
                            "non_field_errors": _(
                                f"Has alcanzado el número máximo de cuentas activas ({max_accounts}) "
                                "para tu plan actual."
                            )
                        }
                    )

            # 2.b) límite de cuentas de inversión por plan
            account_type = attrs.get("type")
            max_investment_accounts = limits.get("max_investment_accounts")
            if (
                account_type == AccountType.INVESTMENT
                and max_investment_accounts is not None
            ):
                current_investment_accounts = Account.objects.filter(
                    owner=user,
                    type=AccountType.INVESTMENT,
                    is_active=True,
                ).count()
                if current_investment_accounts >= max_investment_accounts:
                    raise serializers.ValidationError(
                        {
                            "type": _(
                                f"Has alcanzado el límite de cuentas de inversión "
                                f"({max_investment_accounts}) para tu plan actual."
                            )
                        }
                    )

        # 2.c) límite de cuentas primarias por plan (aplica en create y update)
        if user and attrs.get("is_primary") is True:
            plan = self._get_user_plan(user)
            limits = self._get_plan_limits(plan)
            max_primary = limits.get("max_primary")

            if max_primary is not None:
                qs_primary = Account.objects.filter(
                    owner=user,
                    is_primary=True,
                )
                if has_instance:
                    qs_primary = qs_primary.exclude(pk=instance.pk)

                if qs_primary.count() >= max_primary:
                    raise serializers.ValidationError(
                        {
                            "is_primary": _(
                                f"Has alcanzado el límite de cuentas principales "
                                f"({max_primary}) para tu plan actual."
                            )
                        }
                    )

        return attrs
