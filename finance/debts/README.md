# finance.debts

## Que hace

`finance.debts` modela deudas y cuotas asociadas.

Su responsabilidad actual es:

- CRUD de deudas
- CRUD de cuotas de deuda

## Rol En El Producto

Este contexto permite a Vexxo representar compromisos financieros, no solo
movimientos ya ejecutados.

De cara al usuario sirve para:

- registrar obligaciones
- ver cuotas futuras
- preparar alertas, scheduling o recomendaciones de pago

## Flujo Principal

1. el usuario crea una deuda
2. registra o consulta cuotas asociadas
3. otros contextos pueden usar esa informacion para alertas, planeacion o
   futuros pagos

## Relacion Con Otros Modulos

- `payments`
  puede terminar ejecutando un pago relacionado con una deuda
- `alerts`
  puede detectar vencimientos o friccion futura
- `planning.goals`
  puede convivir con objetivos de reduccion de deuda

## Encaje Con GCP

Hoy es un bounded context CRUD sobre Cloud SQL + Cloud Run.

La evolucion natural seria sumar:

- reglas de vencimiento
- alertas
- integracion con pagos programados

sin cambiar su rol base de representar obligaciones.

## Estado Actual

Hoy expone:

- `DebtViewSet`
- `DebtInstallmentViewSet`

No hay aun automatizacion fuerte ni listeners propios documentados en este
modulo, pero ya define la superficie de deuda y cuota.
