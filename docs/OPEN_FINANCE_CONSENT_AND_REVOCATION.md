# Consentimiento y revocacion de Open Finance

## Alcance

Esta decision aplica a conexiones bancarias de lectura, agregacion de
productos y movimientos. Una autorizacion de datos no autoriza iniciar pagos;
datos y pagos requieren consentimientos independientes.

Esta es una guia tecnica de cumplimiento y no reemplaza la revision juridica
previa a operar con un proveedor real.

## Regla de producto

El usuario conserva control sobre cada conexion:

- conoce entidad, proveedor, finalidad, categorias de datos y vigencia
- otorga autorizacion expresa, informada y no preseleccionada
- puede desconectar desde el mismo canal digital sin barreras
- desconectar detiene nuevas consultas, webhooks aplicables y syncs
- suprimir datos es una solicitud distinta, sujeta a retencion, obligaciones
  legales, seguridad, fraude y auditoria

La interfaz usa **Desconectar**. `revoke` permanece como termino tecnico del
contrato API y del modelo.

## Colombia

La implementacion se guia por:

- [Decreto 1297 de 2022](https://www1.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=190426).
- [Circular Externa 004 de 2024](https://www.superfinanciera.gov.co/publicaciones/10114895/circulares-externas-2024/).
- [Preguntas para consumidores de la SFC](https://www.superfinanciera.gov.co/publicaciones/10114731/innovasfcfinanzas-abiertasfinanzas-abiertas-colombiaconsumidor-financieropeguntas-frecuentes-10114731/).
- [Decreto 0368 de 2026](https://www.minhacienda.gov.co/documents/d/portal/decreto-no-0368-del-07-de-abril-de-2026),
  que establecio el marco obligatorio e integral bajo consentimiento previo,
  expreso e informado.
- Ley 1581 de 2012 y Ley 1266 de 2008 para proteccion de datos personales y
  habeas data financiero.

Consecuencias para Vexxo:

1. El grant identifica usuario, proveedor, proposito, datos, canal y vigencia.
2. La autorizacion del banco se completa en el flujo del proveedor; Vexxo no
   recibe ni almacena credenciales bancarias.
3. La revocacion local surte efecto aunque falle el proveedor: primero se corta
   el acceso en Vexxo y luego se confirma la revocacion remota.
4. Un adapter real no puede declararse disponible sin callback, consulta de
   consentimientos y revocacion remota verificable.
5. Soporte debe demostrar grant, cambios, revocacion, alcance y teardown sin
   conservar secretos ni payloads bancarios completos.

## Referentes internacionales

- Reino Unido: [Open Banking Standards](https://standards.openbanking.org.uk/customer-experience-guidelines/introduction/revocation/latest/)
  exige dashboards faciles de encontrar y sin obstaculos para revocar.
- Brasil: el [Banco Central do Brasil](https://www.bcb.gov.br/meubc/faqs/p/como-cancelar-uma-autorizacao-no-open-finance)
  permite cancelar en cualquier institucion involucrada y exige efecto
  inmediato para intercambio de datos.
- Australia: la [OAIC](https://www.oaic.gov.au/consumer-data-right/consumer-data-right-guidance-for-business/privacy-obligations/consumer-consent%2C-authorisation-and-dashboards)
  exige consentimiento voluntario, expreso, informado, especifico, limitado en
  tiempo y facilmente retirado; separa retiro y eliminacion.
- Union Europea: PSD2 exige consentimiento explicito para acceder a cuentas y
  datos mediante proveedores de servicios autorizados.

Estos referentes no se copian como reglas colombianas. Sostienen un contrato
conservador y portable: control visible, granularidad, expiracion, revocacion
idempotente y evidencia auditable.

## Flujo tecnico

```text
Flutter -> POST connection -> UserConsent(granted) -> OpenBankingConnection
       -> autorizacion proveedor -> productos externos
       -> backend materializa Account owner-scoped -> sync durable -> intake

Flutter -> POST revoke
       -> lock connection
       -> desactivar links y sync futuro
       -> UserConsent(revoked)
       -> marcar connection revoked
       -> notificar y auditar
       -> adapter confirma revocacion remota cuando exista
```

Todo webhook distinto de `connection.revoked` recibido despues de revocar se
rechaza con `connection_revoked`; nunca puede reactivar la conexion.

## Retencion

Al desconectar se conservan por defecto:

- cuentas Vexxo ya materializadas, ahora sin enlace activo
- transacciones del ledger e idempotency receipts
- evidencia minima de consentimiento y revocacion
- auditoria necesaria para integridad, fraude y obligaciones legales

No deben conservarse tokens, credenciales, payloads bancarios crudos ni datos
innecesarios. La futura operacion de supresion debe registrar lo eliminado,
anonimizado o retenido y su fundamento.

## Estado

- `local_mock`: grant, expiracion de prueba, materializacion, sync y revocacion
  local confirmada.
- adapters reales: no disponibles; deben implementar revocacion remota antes
  de habilitarse.
- el endpoint de revocacion es idempotente.
- revocar desde `identity.consents` ejecuta el mismo teardown de conexiones.
- supresion de datos queda como flujo de privacidad independiente.
