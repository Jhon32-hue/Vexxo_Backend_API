# Convencion documental de Vexxo

## Objetivo

Esta guia define como debe organizarse la documentacion del repo para evitar
tres problemas:

- README redundantes que repiten lo mismo
- README viejos que contradicen al codigo
- README utiles pero dificiles de navegar porque cada modulo usa una forma
  distinta

La regla principal es simple:

- cada modulo debe tener un README canonico
- los subREADME deben profundizar una capa concreta, no reescribir todo el
  bounded context

## Tipos de README

### 1. README raiz del repo

Su trabajo es:

- onboarding tecnico
- mapa de arquitectura
- relaciones entre bounded contexts
- flujos transversales
- cloud y eventing
- indice hacia documentos canonicos

No debe convertirse en copia de todos los modulos.

### 2. README canonico de bounded context

Ejemplos:

- `finance/accounts/README.md`
- `finance/transactions/README.md`
- `payments/payment_intents/README.md`
- `identity/users/README.md`
- `alerts/alerts/README.md`

Su trabajo es:

- explicar el ownership del contexto
- dejar el modelo visual local
- documentar flujos y eventos importantes
- describir relacion con otros modulos
- explicar encaje con GCP
- dejar claro el estado actual

### 3. README derivado o de submodulo

Ejemplos:

- `notifications/deliveries/README.md`
- `notifications/listeners/README.md`
- `realtime/consumers/README.md`
- `integrations_stub/banks/README.md`

Su trabajo es:

- profundizar una capa puntual
- explicar su responsabilidad concreta
- enlazar al README canonico del modulo padre

No debe rehacer la explicacion completa del bounded context.

### 4. README de soporte o infraestructura

Ejemplos:

- `common/README.md`
- `backend/README.md`
- `api/README.md`
- `security/README.md`

Su trabajo es:

- explicar primitivas o infraestructura transversal
- documentar contratos, runtime o topologia compartida

## Estructura recomendada

### Para un README canonico de modulo

Orden recomendado:

1. `Que hace`
2. `Documento canonico y subdocumentos` o `Alcance documental`
3. `Rol en el producto`
4. `Vista visual`
5. `Secuencia critica` o `Flujos principales`
6. `Modelos principales` o `Conceptos de negocio`
7. `Relacion con otros modulos`
8. `Encaje con GCP`
9. `Politicas del modulo`
10. `Estado actual`
11. `Pendientes`, `Esqueleto/futuro` o `Nota operativa`

No todos los modulos necesitan todas las secciones, pero la navegacion deberia
parecerse.

### Para un README derivado

Orden recomendado:

1. `Que hace`
2. `Alcance documental`
3. `Vista visual` si aporta claridad
4. `Flujo principal`
5. `Relacion con otros modulos`
6. `Encaje con GCP`
7. `Estado actual`

## Politica de redundancia

Cuando exista un README raiz de modulo y tambien subREADME:

- el README raiz es el mapa canonico del modulo
- los subREADME documentan ownership puntual
- si una explicacion ya vive bien en el README raiz, el subREADME debe
  resumirla y enlazar, no repetirla entera

## Mapa canonico actual

### Contextos fuertes

- `identity.users` es canonico para usuario, plan y usage
- `identity.sessions` es canonico para sesiones
- `identity.devices` es canonico para dispositivos
- `identity.consents` es canonico para consentimientos
- `identity.permissions` es canonico para grants
- `identity.eventing` es canonico para outbox y proyecciones de identidad
- `finance.accounts` es canonico para cuentas y sharing
- `finance.transactions` es canonico para ledger, intake y reconciliacion
- `payments.payment_intents` es canonico para pagos externos
- `alerts.alerts` es canonico para alertas
- `notifications` es canonico para inbox como bounded context
- `realtime` es canonico para la capa realtime como modulo
- `common` es canonico para eventing transversal
- `integrations_stub` es canonico para la frontera temporal de integraciones

### SubREADME derivados con ownership puntual

- `notifications/deliveries`
- `notifications/listeners`
- `realtime/consumers`
- `integrations_stub/banks`
- `payments/scheduled_payments`

## Criterios editoriales

- describir estado actual, no wishful thinking
- distinguir claramente `hoy`, `pendiente` y `futuro`
- no inventar arquitectura distinta a la del codigo
- si cambia un flujo, actualizar el README canonico y el subREADME afectado
- los diagramas deben seguir el mismo lenguaje del dominio
- cuando un modulo ya tenga diagrama en el README raiz, el local debe hacer
  zoom, no copiar exactamente lo mismo

## Regla operativa

Cuando una correccion cambie:

- ownership
- flujo critico
- outbox/eventing
- intake o reconciliacion
- integraciones cloud

entonces deben actualizarse:

1. el README canonico del modulo
2. el README raiz si afecta arquitectura global
3. cualquier subREADME que documente directamente esa capa
