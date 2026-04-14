# integrations

## Objetivo

Esta carpeta contiene la capa documental de mapeo por proveedor.

No es el runtime temporal.

No es el stub.

No es la API del backend.

Su trabajo es dejar trazable, por proveedor, como cada fuente externa se mapea
al contrato canonico correcto.

## Estructura

- `provider_mappings/bank_data/`
- `provider_mappings/payment_execution/`
- `provider_mappings/market_data/`
- `provider_mappings/message_sources/`

## Regla de documentacion

Cada proveedor debe tener un documento propio con:

- categoria primaria
- categoria secundaria si aplica
- bounded context dueno
- contrato canonico
- destino de persistencia
- idempotencia
- consentimiento
- eventos emitidos
- observabilidad minima
- riesgos conocidos

## Documentos relacionados

- [INTEGRATION_SOURCE_CATALOG.md](/D:/Vexxo_Backend_API/INTEGRATION_SOURCE_CATALOG.md)
- [payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md](/D:/Vexxo_Backend_API/payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md)
