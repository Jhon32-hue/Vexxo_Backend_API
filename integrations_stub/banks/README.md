# integrations_stub.banks

## Que hace

Este modulo recibe jobs internos relacionados con cuentas bancarias y los
traduce a llamadas a los servicios canonicos del dominio.

Hoy cubre:

- sync de cuentas
- refresh de inteligencia de `accounts`
- revocacion de acceso por consentimiento/permisos

## Por Que Existe

Mientras `integrations_service` no viva como servicio separado en Cloud Run,
esta carpeta permite trabajar ya con:

- endpoints internos autenticados
- workers
- Cloud Tasks
- callbacks internos

sin duplicar la logica del dominio.

## Flujo De Sync

1. `accounts` agenda sync y emite evento
2. worker o dispatcher llama al endpoint interno stub
3. `integrations_stub.banks.services` delega a
   `finance.accounts.services.account_sync_service`
4. el estado monotono de sync se actualiza en `accounts`

## Flujo De Inteligencia

1. un evento o dispatcher pide refresh
2. el endpoint interno recibe `owner_id`
3. el stub delega a `finance.accounts.services.intelligence_service`

## Flujo De Revocacion

1. `identity` o consentimiento emite evento
2. el endpoint interno recibe usuario/proveedor
3. el stub delega a
   `finance.accounts.services.user_integration_service`

## Relacion Con Otros Modulos

- `finance.accounts`: dueño real del lifecycle de sync
- `identity`: fuente de lifecycle y consentimiento
- `common.domain_events`: transporte/eventos que disparan el trabajo

## Encaje Con GCP

Este modulo esta diseñado para ser reemplazado casi 1:1 por un servicio
externo:

- hoy puede recibir Cloud Tasks o jobs internos
- mañana puede vivir en Cloud Run separado
- los tokens internos ya preparan ese camino

La semantica correcta es:

- el stub recibe
- el dominio decide
- el estado vuelve a cuentas e identidad
