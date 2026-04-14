# Salt Edge

## Clasificacion

- categoria primaria: `bank_data`
- bounded context principal: `finance.accounts` + `finance.transactions`
- contrato canonico: `open_banking.normalized_payload`

## Reglas clave

- no escribir ledger directo
- requiere consentimiento y control de expiracion
- debe preservar `provider_account_id`, cursor y trazabilidad de sync
