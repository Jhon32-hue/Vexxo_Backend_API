# integrations

## Responsabilidad

Esta carpeta es la frontera canonica de integraciones externas. Contiene los
mapeos contractuales por proveedor y los runtimes que ya tienen estado y
lifecycle propios. No contiene reglas contables ni credenciales.

## Estructura

- `open_banking/`: consentimiento, conexiones, enlaces a cuentas, webhooks y
  catalogo seguro de proveedores bancarios.
- `credentials/`: envelopes cifrados y lifecycle de tokens/secretos externos.
- `provider_mappings/bank_data/`: normalizacion de datos bancarios.
- `provider_mappings/payment_execution/`: contratos de ejecucion de pagos.
- `provider_mappings/market_data/`: fuentes de mercado.
- `provider_mappings/message_sources/`: SMS, voz y otras entradas.

`integrations_stub` sigue existiendo como receptor local temporal para jobs
que aun no tienen adapter real. No es fuente de verdad ni un segundo dominio.

## Regla para nuevos proveedores

Cada adapter debe declarar proveedor, bounded context propietario, contrato
canonico, consentimiento, idempotencia, firma de webhook, datos persistidos,
eventos, observabilidad y estrategia de revocacion. Los secretos bootstrap se
inyectan por variables de entorno y nunca se versionan. Los tokens dinamicos
emitidos por proveedores viven en `IntegrationCredential`, nunca en metadata,
eventos o respuestas mobile.

Documentos relacionados:

- [Catalogo de fuentes](../INTEGRATION_SOURCE_CATALOG.md)
- [Contratos de pagos](../payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md)
- [Open Banking](open_banking/README.md)
