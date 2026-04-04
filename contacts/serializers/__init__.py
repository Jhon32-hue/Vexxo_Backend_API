# contacts.serializers

## Que hace

Este directorio transforma el modelo `Contact` en superficie API.

## Pieza Principal

- `contact_serializer.py`

## Responsabilidad

El serializer actual:

- expone `Contact`
- agrega `net_status`
- deja campos contables como read-only
- toma la moneda preferida del usuario si no viene una moneda explicita
- fija `owner` al crear usando el request autenticado

## Relacion Con Otras Piezas

- `contacts.models`
  fuente de verdad del contacto.
- `contacts.views`
  usa este serializer para CRUD y acciones.

## Estado Actual

La capa de serializacion es simple pero funcional y alineada con el modulo
operativo actual de contactos.
