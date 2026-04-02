# contacts.models

## Que hace

Este directorio contiene el modelo canonico `Contact` del modulo `contacts`.

## Pieza Principal

- `contact.py`

## Responsabilidad

Modelar una contraparte financiera reutilizable del usuario con:

- datos basicos de identificacion
- relacion personal o comercial
- balance neto
- actividad reciente
- vinculacion opcional a un usuario real de Vexxo

## Relacion Con Otras Piezas

- `contacts.serializers`
  expone el modelo a la API.
- `contacts.views`
  aplica ownership, filtros y acciones HTTP.
- `finance.transactions`
  aporta el dato real para recalcular `net_balance`.

## Estado Actual

Este subdirectorio si contiene logica de dominio visible y activa, en contraste
con otros contextos del repo que hoy siguen en scaffold.
