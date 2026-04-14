# SMS Bank Template

## Clasificacion

- categoria primaria: `message_inferred`
- bounded context principal: `finance.transactions`
- contrato canonico: `message_inferred.normalized_payload`

## Reglas clave

- parser versionado
- confidence score obligatorio
- no tratarlo como open banking
- reconciliar despues contra fuente bancaria real si aparece
