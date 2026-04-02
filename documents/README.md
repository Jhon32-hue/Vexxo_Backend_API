# documents

## Que hace

`documents` agrupa capacidades documentales del producto:

- archivo o storage
- metadata
- OCR
- vinculos con transacciones
- futuros artefactos o soportes compartidos

## Estado Actual

Hoy todos los submodulos visibles de `documents` siguen en scaffold:

- `files`
- `links_to_transactions`
- `metadata`
- `ocr_requests`
- `storage`

No detecte en esta pasada una superficie operativa equivalente a los contextos
core ya maduros.

## Rol En El Producto

Este bloque es importante para una app financiera personal porque permite
capturar y conectar:

- facturas
- comprobantes
- recibos
- soportes para impuestos o conciliacion
- resultados OCR

## Relacion Con Otros Modulos

- `finance.transactions`
  destino natural de comprobantes y vinculos documentales.
- `payments`
  soporte de pagos, reversos o settlement.
- `reports.exports`
  generacion o archivo de artefactos.
- `social.documents_shared`
  futura capa de documentos compartidos.

## Encaje Con GCP

Este bounded context tiene un encaje cloud muy claro:

- Cloud Storage para binarios y artefactos
- Cloud SQL para metadata y vinculos
- Document AI o servicios OCR externos para extraccion
- workers o callbacks para pipelines asincronos

## Estado Actual

La intencion arquitectonica esta clara, pero la implementacion funcional todavia
no aparece aqui como producto cerrado.
