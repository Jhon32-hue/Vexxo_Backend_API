# tasks.dispatchers

## Que hace

Este directorio agrupa dispatchers pensados para enviar trabajo o eventos a
infraestructura de ejecucion externa.

## Archivos Presentes

- `cloud_tasks.py`
- `pubsub.py`
- `scheduler.py`

## Rol Esperado

La responsabilidad natural de estos archivos es traducir una intencion del
sistema a:

- una tarea HTTP en Cloud Tasks
- un mensaje en Pub/Sub
- una programacion o trigger de Scheduler

## Casos De Uso

- sacar trabajo pesado del request path
- delegar fan-out a consumidores externos
- programar ejecucion diferida o recurrente
- encapsular transporte cloud sin contaminar el dominio

## Estado Actual

En esta pasada no detecte logica visible o consolidada dentro de estos archivos,
asi que deben leerse como fronteras preparadas mas que como adapters ya
cerrados.

## Encaje Con GCP

Este subdirectorio es uno de los lugares mas directos para expresar la
topologia cloud del proyecto cuando madure mas.
