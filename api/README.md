# api

## Que hace

`api` es la superficie HTTP principal del backend.

Su responsabilidad es:

- exponer rutas versionadas
- agrupar bounded contexts bajo una convencion coherente
- servir como BFF para mobile y web
- mantener una frontera clara entre request/response y logica de dominio

## Rol En El Producto

Para mobile/web, este modulo es la puerta de entrada a:

- identidad y plan
- cuentas y ledger
- pagos
- alertas
- notificaciones
- realtime persistido
- soporte y auditoria operativa

No debe concentrar la logica de negocio profunda. Esa vive en serializers,
services, modelos y bounded contexts.

## Versionado y estructura

El punto de entrada principal hoy es [api/v1/routers.py](v1/routers.py).

La organizacion actual separa:

- `identity/*`
- `finance/*`
- `planning/*`
- `social/*`
- `payments/*`
- `alerts/*`
- `notifications/*`
- `realtime/*`
- `support/*`

## Por Que Existe

Aunque la logica fuerte viva en cada contexto, el backend necesita una
superficie uniforme para mobile/web.

`api` evita:

- rutas dispersas sin convencion
- acoplar la app a detalles internos del monolito
- mezclar controllers HTTP con logica de negocio profunda

## Flujo General

1. mobile/web llama un endpoint versionado
2. DRF enruta al módulo correspondiente
3. serializers validan input
4. el bounded context ejecuta el caso de uso
5. si hace falta trabajo pesado, se emite evento o se agenda worker
6. la respuesta HTTP vuelve rapido al cliente

## Runtime actual

La superficie corre localmente en Django/DRF sobre PostgreSQL. Los trabajos
pesados salen del request mediante outbox y workers durables.

Regla importante:

- el API no debe depender de conexiones largas
- el API ordena, valida y responde
- el procesamiento fuerte vuelve por eventos, polling o workers locales

## Relacion Con Otros Modulos

- enruta a todos los bounded contexts principales
- refleja la estrategia de producto y la segmentacion de dominio
- sirve como capa estable para mobile aunque cambien integraciones internas

## Politicas De Diseño

- endpoints claros por bounded context
- versionado por namespace (`v1`)
- acciones de dominio explicitas cuando un CRUD no alcanza
- respuestas rápidas y compatibles con flows asincronos

## Estado Actual

Hoy `api` ya enruta identidad, finanzas, pagos, alertas, notificaciones,
realtime y soporte.

La evolucion natural no es cargar mas logica aqui, sino:

- mantener contratos estables para mobile
- mover trabajo pesado a workers y callbacks
- seguir versionando la superficie cuando cambien contratos publicos
