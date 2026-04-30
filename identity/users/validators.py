from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UppercaseLowercaseDigitPasswordValidator:
    def validate(self, password, user=None):
        value = str(password or "")
        if not any(ch.isupper() for ch in value):
            raise ValidationError(_("La contrasena debe incluir al menos una mayuscula."))
        if not any(ch.islower() for ch in value):
            raise ValidationError(_("La contrasena debe incluir al menos una minuscula."))
        if not any(ch.isdigit() for ch in value):
            raise ValidationError(_("La contrasena debe incluir al menos un numero."))

    def get_help_text(self):
        return _("Tu contrasena debe incluir mayusculas, minusculas y numeros.")
