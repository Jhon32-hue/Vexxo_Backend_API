# security

## Que hace

`security` agrupa piezas transversales relacionadas con proteccion de datos,
politicas y señales de riesgo.

## Archivos Presentes

Hoy el directorio contiene:

- `encryption.py`
- `fraud_signals.py`
- `pii_masking.py`
- `policies.py`
- `rate_limits.py`

## Estado Del Codigo

En esta pasada no detecte implementacion funcional visible dentro de esos
archivos. Se comportan como placeholders o fronteras preparadas, no como un
subdominio operativo ya consolidado.

## Rol Esperado

El nombre y la organizacion del directorio son coherentes con necesidades reales
de Vexxo:

- cifrado de datos sensibles
- enmascaramiento de PII en logs o soporte
- politicas de seguridad reutilizables
- señales de fraude o riesgo
- rate limiting transversal

## Casos De Uso Naturales

- proteger secrets y material criptografico
- enmascarar datos sensibles en logs o vistas internas
- expresar politicas reutilizables de seguridad
- detectar señales tempranas de fraude o abuso
- endurecer limites de acceso o consumo

## Relacion Con Otros Modulos

- `identity`
  autenticacion, sesiones, dispositivos y step-up.
- `payments`
  fraude, reversos, riesgo y limites operativos.
- `support.audit`
  trazabilidad de operaciones sensibles.
- `observability`
  cuidado de datos sensibles en logs y metricas.

## Encaje Con GCP

Este bloque esta alineado con:

- Cloud KMS para material criptografico
- Secret Manager para secretos
- Cloud Armor y API Gateway para borde y WAF
- Cloud Logging con politicas de redaccion o masking

## Estado Actual

Hoy debe leerse como una frontera tecnica preparada, no como una capa de
seguridad fully wired dentro del repo. Parte de la seguridad efectiva visible
hoy vive dispersa en `backend.settings`, `identity`, `payments` y `support`.
