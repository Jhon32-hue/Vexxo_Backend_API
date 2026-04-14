# Belvo

## Clasificacion

- categoria primaria: `bank_data`
- bounded context principal: `finance.accounts` + `finance.transactions`
- contrato canonico: `open_banking.normalized_payload`

## Persistencia esperada

- linkage de cuenta externa en `finance.accounts`
- movimientos en `TransactionIntakeBatch` / `TransactionIntakeReceipt`
- ledger final en `Transaction`

## Reglas clave

- no escribir ledger directo
- dedupe por identidad externa y fingerprint
- requiere consentimiento y trazabilidad de conexion
