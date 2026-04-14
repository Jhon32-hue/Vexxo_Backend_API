# finance.fx

## Que hace

`finance.fx` gestiona snapshots de tasas de cambio.

Documento complementario recomendado:

- [Catalogo de fuentes e integraciones](/c:/Users/Alamb/Documents/Vexxo_Backend_API/INTEGRATION_SOURCE_CATALOG.md)

Su responsabilidad actual es:

- CRUD operativo de `ExchangeRate`
- consulta de tasas ya persistidas

## Rol En El Producto

Este modulo permite que Vexxo:

- convierta montos entre monedas
- explique exposicion cambiaria
- soporte cuentas o productos multicurrency

## Flujo Principal

1. una tasa se persiste como snapshot
2. el API la expone ordenada por `observed_at`
3. otros contextos pueden usarla para conversion o analitica

## Relacion Con Otros Modulos

- `finance.accounts`
  puede apoyarse en FX para exposicion por moneda
- `reports`
  puede requerir conversiones o lecturas multicurrency
- `payments`
  puede necesitar contexto cambiario en ejecucion futura

## Encaje Con GCP

Hoy este contexto es principalmente OLTP.

La ingestion real de tasas deberia evolucionar a:

- job o integracion externa
- Cloud Scheduler / worker
- posible persistencia posterior en BigQuery para analitica

## Estado Actual

El viewset actual (`TasaFXViewSet`) expone CRUD de snapshots ya persistidos.

Importante:

- hoy no trae tasas de internet por si mismo
- la ingesta real debe vivir en un servicio o worker aparte
