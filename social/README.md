# social

## Que hace

`social` agrupa contextos relacionados con colaboracion, pertenencia y
experiencias compartidas entre usuarios.

No todos los submodulos estan igual de maduros. Hoy conviven:

- un modulo operativo claro: `social.teams`
- varios contextos reservados o scaffold:
  - `chat`
  - `contacts`
  - `documents_shared`
  - `groups`
  - `invitations`
  - `memberships`
  - `shared_expenses`

## Rol En El Producto

Vexxo no solo quiere mostrar dinero individual. Tambien busca soportar
colaboracion real:

- trabajo en equipo
- gastos compartidos
- invitaciones
- pertenencias y grupos

## Relacion Con Otros Modulos

- `finance.accounts`
  sharing financiero y membresias operativas.
- `planning.shared_goals`
  metas compartidas futuras.
- `documents`
  contenido o comprobantes compartibles.
- `notifications` y `realtime`
  feedback para experiencias colaborativas.

## Encaje Con GCP

Estos contextos pueden evolucionar en Cloud Run y Cloud SQL, con realtime
liviano o consumidores dedicados si la experiencia colaborativa crece.

## Estado Actual

`social.teams` es hoy la pieza mas concreta del bloque social. Los demas
submodulos deben leerse como contexto reservado salvo que su README indique una
superficie funcional mas real.
