# FX Provider Template

## Clasificacion

- categoria primaria: `market_data`
- bounded context principal: `finance.fx`
- contrato canonico: `fx_rate.normalized_payload`

## Reglas clave

- no crear `Transaction`
- timestamp de observacion obligatorio
- proveedor y par de monedas obligatorios
