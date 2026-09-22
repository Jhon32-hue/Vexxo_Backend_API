# documents.metadata

`DocumentMetadata` conserva metadata auxiliar de un comprobante: origen de
captura, pistas de comercio, monto, moneda y atributos adicionales.

La relacion con `DocumentFile` es uno-a-uno. Estos campos son pistas no
autoritativas: no modifican el ledger ni crean pagos. Cualquier efecto
financiero requiere una accion visible y una API canonica de dominio.

El siguiente cierre es una API versionada de correccion humana que conserve la
procedencia de cada campo y no sobrescriba silenciosamente la extraccion
original.
