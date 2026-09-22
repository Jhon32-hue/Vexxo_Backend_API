# documents.storage

Esta frontera define donde viven los binarios privados. En el runtime local el
backend efectivo es Django `FileSystemStorage` bajo `.runtime/media`; la ruta no
se expone como URL publica y el nombre fisico se aleatoriza por UUID.

La integridad se verifica en `documents.files` mediante SHA-256. No se agrega
un adapter abstracto hasta que exista un segundo backend real: anticiparlo ahora
solo duplicaria la interfaz de Django sin aportar aislamiento.

Antes de crecer se requiere definir retencion, borrado fisico diferido,
autorizacion temporal de descarga y backup de media independiente del backup de
PostgreSQL.
