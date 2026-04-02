# contacts.views

## Que hace

Este directorio expone la API HTTP del modulo `contacts`.

## Pieza Principal

- `contact_view.py`

## Responsabilidad

`ContactViewSet`:

- lista solo contactos del usuario autenticado
- filtra por relacion, archivado y estado financiero
- valida limite por plan al crear
- permite archivar y desarchivar

## Casos De Uso

- crear un contacto nuevo
- buscar contactos por nombre o telefono
- ver a quien debes o quien te debe
- ocultar contactos archivados sin borrar historial financiero

## Relacion Con Otras Piezas

- `contacts.serializers`
  entrada y salida de datos.
- `identity.users`
  policy de plan para cantidad de contactos.
- `finance.transactions`
  impacto indirecto via balance neto del contacto.

## Estado Actual

La superficie HTTP es funcional hoy y responde a un caso de uso real del
producto, no a un scaffold vacio.
