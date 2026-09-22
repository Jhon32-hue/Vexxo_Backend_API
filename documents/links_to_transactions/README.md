# documents.links_to_transactions

`DocumentTransactionLink` asocia un documento privado con una transaccion del
mismo propietario sin introducir el binario o el OCR dentro del ledger.

La API autenticada vive en `/api/documents/transaction-links/`. Los querysets y
serializers validan ownership de documento y transaccion; la restriccion
`document + transaction + relationship` evita relaciones duplicadas.

La relacion sirve como evidencia o soporte, no como autorizacion para alterar
montos, estados o conciliacion. Falta cerrar la UX mobile de vinculacion y la
politica ante soft delete del documento.
