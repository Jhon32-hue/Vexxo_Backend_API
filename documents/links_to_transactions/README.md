# documents.links_to_transactions

## Que hace

`documents.links_to_transactions` existe para asociar documentos con
transacciones u otros movimientos financieros.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Por Que Existe

En Vexxo es valioso poder conectar:

- una transaccion
- un pago
- un comprobante o factura

sin meter todo ese detalle dentro del ledger mismo.

## Relacion Con Otros Modulos

- `finance.transactions`
  ledger canonico.
- `payments`
  pagos externos y soportes operativos.
- `documents.files`
  archivo base.
- `documents.metadata`
  enrichment del documento.

## Estado Actual

Todavia no hay implementacion publica visible, pero el contexto es correcto y
coherente con la arquitectura general.
