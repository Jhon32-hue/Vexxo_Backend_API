# finance.vendors

## Que hace

`finance.vendors` administra contrapartes o comercios asociados a movimientos
financieros.

Su responsabilidad actual es:

- CRUD de proveedores/comercios
- servir como dimension reutilizable para ledger, pagos y analitica

## Rol En El Producto

De cara al usuario, los vendors ayudan a entender:

- con quien gasta o recibe dinero
- recurrencia de pagos a terceros
- historial por comercio o contraparte

## Flujo Principal

1. se crea o edita un `Vendor`
2. `transactions` o `payments` pueden referenciarlo
3. reportes, busquedas y experiencias futuras se apoyan en esa relacion

La API solo lista y modifica vendors del usuario autenticado. El `owner` se
asigna en el servidor y no puede suplantarse desde el payload.

## Flujo De Soporte

Soporte puede ver en una vista interna auditada que el usuario tiene actividad
asociada, pero no obtiene automaticamente importes ni detalles de sus
transacciones. Una inspeccion mas profunda debe partir de un caso y permisos
explicitos.

## Relacion Con Otros Modulos

- `finance.transactions`
  usa vendor como parte del ledger
- `payments.payment_intents`
  puede asociar un vendor al intent externo
- `payments.scheduled_payments`
  puede heredar vendor al template recurrente

## Runtime Local

Es una pieza OLTP simple en PostgreSQL local y no necesita worker propio.

Su informacion es relevante para reportes y recomendaciones futuras.

## Estado Actual

Hoy expone `ProveedorViewSet` como CRUD autenticado y aislado por propietario
sobre `Vendor`.

Sigue siendo una capa sencilla, pero forma parte de la semantica del negocio y
no deberia tratarse como mero dato auxiliar.

El siguiente cierre funcional es normalizacion y deduplicacion de aliases por
usuario, no una integracion cloud.
