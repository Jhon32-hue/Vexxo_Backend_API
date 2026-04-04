# scripts

## Que hace

`scripts` contiene utilidades operativas y de mantenimiento fuera del request
path normal del backend.

## Archivos Presentes

- `backfill_events.py`
- `bootstrap.py`
- `generate_reports.py`
- `migrate_data.py`

## Estado Del Codigo

En esta pasada no detecte implementacion funcional visible dentro de esos
archivos. Por eso conviene documentarlos por su rol estructural y no como
herramientas cerradas.

Eso aplica a los scripts Python listados arriba. Los wrappers `.cmd` locales no
versionados si tienen una responsabilidad operativa concreta: ejecutar
`manage.py` contra PostgreSQL local `Vexxo` sin tocar el `.env` cloud.

## Rol En El Sistema

Este directorio es el lugar correcto para:

- bootstrap local o de entorno
- backfills de eventos o proyecciones
- migraciones de datos extraordinarias
- generacion puntual de reportes o artefactos

## Criterio De Uso

Los scripts aqui no deben reemplazar logica de aplicacion estable. Su espacio es
para:

- operaciones puntuales
- bootstrap
- mantenimientos o migraciones controladas
- backfills excepcionales

## Runner Local Para PostgreSQL `Vexxo`

### Alcance

Estos wrappers son solo para desarrollo local y debugging de ingenieria.

No deben quedar versionados en Git. La convención local esperada es:

- `scripts/run_manage_vexxo_app.cmd`
- `scripts/migrate_vexxo_app.cmd`
- `scripts/test_transactions_vexxo_app.cmd`

No son para:

- produccion
- Cloud Run
- jobs cloud
- pipelines de despliegue
- automatizacion operativa sobre GCP

Pueden existir localmente en la máquina del desarrollador, pero no deben
tratarse como scripts de release ni como artefactos del repositorio.

### Que significa "por sesion"

Cuando se usa una configuracion "por sesion", las variables de entorno viven
solo en la consola actual:

- no modifican el archivo `.env`
- no cambian la configuracion cloud del proyecto
- desaparecen al cerrar la terminal

Ademas, los wrappers `.cmd` usan `setlocal`, asi que las variables internas del
script (`ENV=local`, `DB_ENGINE`, `DB_NAME`, etc.) tampoco se fugan fuera del
proceso del script.

### Credenciales y overrides

Por seguridad, la contrasena no queda hardcodeada en el repo. Debe venir por:

- `VEXXO_APP_DB_PASSWORD`

Tambien puedes overridear:

- `VEXXO_APP_DB_NAME`
- `VEXXO_APP_DB_USER`
- `VEXXO_APP_DB_HOST`
- `VEXXO_APP_DB_PORT`

Si no haces overrides, los wrappers asumen:

- base: `Vexxo`
- usuario: `postgres`
- host: `127.0.0.1`
- puerto: `5432`

### Comandos de uso

Desde PowerShell:

```powershell
$env:VEXXO_APP_DB_PASSWORD='Colsander32'
.\scripts\migrate_vexxo_app.cmd
.\scripts\test_transactions_vexxo_app.cmd
```

Para cualquier otro comando Django:

```powershell
$env:VEXXO_APP_DB_PASSWORD='Colsander32'
.\scripts\run_manage_vexxo_app.cmd showmigrations
.\scripts\run_manage_vexxo_app.cmd shell
.\scripts\run_manage_vexxo_app.cmd test finance.transactions.tests --verbosity 2 --keepdb
```

### Que resuelve

Este flujo resuelve cuatro problemas practicos:

- evita editar el `.env` cada vez que quieres salir de Cloud SQL
- deja `ENV=local` solo para la corrida actual
- reduce errores manuales al repetir `migrate` y `test`
- permite validar el backend sobre PostgreSQL real antes de mover cambios a GCP

## Relacion Con Otros Modulos

- `common` e `identity.eventing`
  candidatos naturales para backfills.
- `reports`
  generacion extraordinaria de reportes.
- `finance` y `payments`
  migraciones o normalizacion de datos historicos.

## Encaje Con GCP

Cuando estas piezas se formalizan en cloud, suelen migrar a:

- Cloud Run jobs
- scripts internos de CI/CD
- tareas ad-hoc operadas desde pipelines

Los wrappers locales no reemplazan ese camino cloud. Su funcion es acelerar
desarrollo, debugging y validacion local con un flujo consistente.

## Estado Actual

Directorio util y bien ubicado, pero sus scripts no deben asumirse como
herramientas listas de produccion sin revisar su contenido concreto.

Hoy, la parte operativa mas util y validada del directorio es el runner local
de `manage.py` sobre `Vexxo`.
