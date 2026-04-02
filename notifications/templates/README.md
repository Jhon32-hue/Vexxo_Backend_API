# notifications.templates

## Que hace

`notifications.templates` existe para alojar plantillas reutilizables de
mensajeria:

- textos base
- variantes por canal
- parametros dinamicos
- versionado de contenido

## Estado Del Codigo

Hoy este modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin plantilla persistente o servicio publico detectado

## Rol En El Producto

En Vexxo las notificaciones no son solo un log tecnico. Son parte de la
experiencia del usuario. Un contexto de templates permite:

- unificar copy entre inbox, push y email
- mantener consistencia con negocio y soporte
- separar contenido de la logica que detecta el evento

## Relacion Con Otros Modulos

- `notifications.listeners`
  decide cuando y a quien notificar.
- `notifications.deliveries`
  materializa el mensaje generado.
- `alerts`
  puede originar mensajes derivados de alertas o IA.
- `support.audit`
  ayuda a rastrear que se genero y por que.

## Encaje Con GCP

Mas adelante este modulo podria trabajar con:

- Cloud Run para administracion y render
- Cloud SQL para plantillas y versionado
- Cloud Storage si aparecen artefactos ricos o assets
- workers para rendering o entrega por canal

## Estado Actual

Hoy el sistema genera mensajes desde listeners y servicios, sin un repositorio
formal de templates en este modulo.
