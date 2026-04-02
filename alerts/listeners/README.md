# alerts.listeners

## Que hace

`alerts.listeners` existe como contexto reservado para listeners dedicados a
construir o disparar alertas desde eventos del dominio.

## Estado Del Codigo

Hoy el app esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin handlers propios detectados en este paquete

## Relacion Con Otros Modulos

La logica operativa que hoy si existe para alertas derivadas y enriquecimiento
vive principalmente en:

- `alerts.alerts`
- `alerts.rules`
- `alerts.alerts.dispatch_service`
- `alerts.alerts.event_handlers`

Por eso este modulo no debe documentarse como cerrado o productivo hoy.

## Encaje Con El Negocio

El nombre del contexto sigue teniendo sentido: Vexxo necesita escuchar cambios
de cuentas, transacciones, pagos o metas y convertirlos en alertas utiles.
Solo que hoy ese trabajo no esta centralizado aqui.

## Encaje Con GCP

Si mas adelante se separa un servicio de listeners de alertas, este modulo es
un candidato natural para:

- consumidores Pub/Sub
- workers en Cloud Run
- pipelines async que terminen creando `Alert`

## Estado Actual

Hoy es una reserva estructural. La capa productiva actual de alertas esta en
otros submodulos del contexto `alerts`.
