# finance.budgets

## Que hace

`finance.budgets` existe como bounded context reservado para presupuestos.

## Estado Actual

Hoy el modulo existe en estructura, pero no expone una superficie documentada
equivalente a otros dominios core del backend:

- no detecté rutas públicas del contexto
- no detecté una capa visible de servicios o views consolidada en esta pasada

## Rol Esperado

Cuando madure, debería cubrir:

- presupuestos por periodo
- control por categoria o cuenta
- alertas de desborde
- relacion con reportes y recomendaciones

## Relacion Esperada

- `finance.transactions`
  para consumo real vs presupuesto
- `alerts`
  para avisos de over/under budget
- `reports`
  para lectura agregada

## Encaje Con GCP

Debería seguir la misma filosofia del resto:

- OLTP claro en Cloud SQL
- proyecciones y analytics fuera del request path
- eventos si se vuelve relevante para alertas o growth

## Nota

Este README existe para no dejar el hueco documental oculto.
No debe interpretarse como modulo funcional completo al nivel de `accounts` o
`payments`.
