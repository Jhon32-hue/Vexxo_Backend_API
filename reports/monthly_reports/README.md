# reports.monthly_reports

## Responsabilidad

Materializa un cierre mensual reproducible por `owner + month + currency`.
Solo admite meses terminados en la zona horaria solicitada.

## Contrato

- `POST /api/reports/monthly-closes/`
- `GET /api/reports/monthly-closes/`
- el primer cierre crea version 1
- repetir sin `regenerate` devuelve el cierre vigente
- regenerar exige `reason` y crea una nueva version enlazada por `supersedes`
- nunca se sobrescribe un snapshot anterior

El snapshot incluye cashflow confirmado y el overview de presupuestos del mes.
Las transacciones se filtran por moneda de la cuenta; no se hace conversion FX
implicita.

```json
{
  "month": "2026-08",
  "currency": "COP",
  "timezone": "America/Bogota",
  "regenerate": false,
  "reason": ""
}
```

## Limites

- no existe cierre automatico: es una operacion explicita
- no existe PDF todavia
- la retencion legal definitiva depende de jurisdiccion y politica de negocio
