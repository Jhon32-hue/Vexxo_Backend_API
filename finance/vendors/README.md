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

## Relacion Con Otros Modulos

- `finance.transactions`
  usa vendor como parte del ledger
- `payments.payment_intents`
  puede asociar un vendor al intent externo
- `payments.scheduled_payments`
  puede heredar vendor al template recurrente

## Encaje Con GCP

Es una pieza OLTP simple en Cloud SQL, expuesta por Cloud Run.

No necesita workers propios, pero su informacion es relevante para reportes,
analytics y futuras recomendaciones.

## Estado Actual

Hoy expone `ProveedorViewSet` como CRUD base sobre `Vendor`.

Sigue siendo una capa sencilla, pero forma parte de la semantica del negocio y
no deberia tratarse como mero dato auxiliar.
