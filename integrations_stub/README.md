# integrations_stub

## Que hace

`integrations_stub` es un conjunto de receptores internos temporales que simulan
el rol de futuros servicios externos o separados.

Su objetivo es permitir que los bounded contexts ya trabajen con:

- eventos
- jobs internos
- callbacks
- workers

sin obligar a tener desde el primer dia todos los microservicios separados.

## Rol En La Arquitectura

Este modulo permite que el dominio se diseñe como si ya existieran:

- `integrations_service`
- `llm_gateway`
- servicios OCR/ML
- workers externos

pero ejecutando aun dentro del mismo repositorio.

## Por Que Existe

Este modulo permite diseñar desde ya con fronteras cloud-native aunque la
separacion fisica de servicios llegue despues.

Eso evita que el monolito se acople a llamadas directas imposibles de extraer.

## Principio

El dominio no debe depender del stub. El stub depende del dominio.

Eso significa:

- las reglas reales viven en `accounts`, `payments`, `alerts`, etc.
- el stub solo recibe trabajo y delega al servicio canonico

## Encaje Con GCP

Este modulo es el puente natural para migrar a:

- Cloud Run services separados
- Cloud Tasks
- Pub/Sub consumers
- callbacks HTTP internos

Cuando el servicio real exista, el ideal es mover el receptor y dejar intacta
la semantica del caso de uso.

## Submodulos actuales

- `banks`
  sync de cuentas, refresh de inteligencia y revocacion de consentimientos
- `llm`
  frontera temporal para tareas de IA
- `ocr`
  frontera temporal para OCR/documentos
- `payments`
  frontera temporal para rails externos de pago
- `ml`
  frontera temporal para pipelines o inferencia

## Que no debe pasar

- no debe duplicar logica del bounded context real
- no debe convertirse en segundo dominio
- no debe inventar contratos incompatibles con el servicio futuro

## Estado Actual

Hoy actua como receptor temporal para bancos, IA, OCR, ML y pagos.

La regla sigue siendo:

- el stub recibe y traduce
- el servicio canonico del dominio decide
- la extraccion a Cloud Run futuro debe ser incremental, no traumática
