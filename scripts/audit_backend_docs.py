"""Rebuild source evidence in module READMEs without importing Django."""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- backend-source-audit:start -->'
END = '<!-- backend-source-audit:end -->'
DOMAINS = {'admin_tools', 'alerts', 'api', 'backend', 'common', 'contacts',
           'documents', 'finance', 'identity', 'integrations', 'integrations_stub',
           'notifications', 'observability', 'payments', 'planning', 'realtime',
           'reports', 'security', 'social', 'support', 'tasks'}
PARSE_ERRORS = {}


def sources(directory):
    return sorted(p for p in directory.rglob('*.py')
                  if not {'migrations', '__pycache__'}.intersection(p.parts)
                  and not p.name.startswith('test'))


def parse(path):
    return ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))


def keys(path, name):
    for node in ast.walk(parse(ROOT / path)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ) and isinstance(node.value, ast.Dict):
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    return []


def module_section(readme):
    directory = readme.parent
    module = directory.relative_to(ROOT).as_posix().replace('/', '.')
    files = sources(directory)
    digest = hashlib.sha256()
    models, routes, dependencies, layers = [], [], set(), {}
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        digest.update(relative.encode() + b'\0' + raw)
        try:
            tree = parse(path)
        except SyntaxError as exc:
            PARSE_ERRORS[relative] = f'linea {exc.lineno}: {exc.msg}'
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                if any(b.endswith('Model') or b.endswith('Outbox') or
                       b.endswith('BaseModel') for b in bases):
                    models.append((node.name, relative))
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                target = node.module.split('.')[0]
                if target in DOMAINS and target != module.split('.')[0]:
                    dependencies.add(target)
            if path.name.endswith('urls.py') or path.name == 'routers.py':
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'register':
                    if node.args and isinstance(node.args[0], ast.Constant):
                        routes.append((str(node.args[0].value) + '/ [DRF router]', relative))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'path', 're_path'}:
                    if node.args and isinstance(node.args[0], ast.Constant):
                        routes.append((str(node.args[0].value), relative))
        lowered = relative.lower()
        for layer in ('services', 'serializers', 'views', 'listeners', 'models', 'management'):
            if layer in lowered:
                layers.setdefault(layer, []).append(relative)
    rel = lambda p: Path(__import__('os').path.relpath(ROOT / p, directory)).as_posix()
    lines = [START, '## Evidencia del codigo y mapa de dependencias', '',
             'Inventario estatico reproducible del checkout. Describe declaraciones e imports;',
             'no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.',
             'Las rutas son locales a su URLConf: el prefijo publico se consulta en',
             f'[`api/v1/routers.py`]({rel("api/v1/routers.py")}).', '',
             f'- Archivos Python de implementacion: **{len(files)}** (excluye tests y migraciones).',
             f'- Huella SHA-256 del codigo inventariado: `{digest.hexdigest()}`.',
             f'- Familias detectadas: {", ".join(sorted(layers)) or "sin capas convencionales detectadas"}.', '']
    if models:
        lines += ['### Declaraciones de modelos detectadas', '']
        lines += [f'- `{name}` en [{p}]({rel(p)}).' for name, p in sorted(set(models))]
        lines += ['']
    if routes:
        lines += ['### Rutas declaradas', '', '| Patron local | Fuente |', '| --- | --- |']
        lines += [f'| `{route.replace("|", "&#124;")}` | [{p}]({rel(p)}) |'
                  for route, p in sorted(set(routes))]
        lines += ['']
    else:
        lines += ['No se detectan declaraciones `path`/`re_path` propias en este alcance.',
                  'Esto no implica que el modulo carezca de consumidores internos.', '']
    lines += ['### Diagrama de dependencia estatica', '',
              'Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.',
              '', '```mermaid', 'flowchart LR', f'    M["{module}"]']
    if dependencies:
        lines += [f'    M --> D{i}["{d}"]' for i, d in enumerate(sorted(dependencies))]
    else:
        lines += ['    M --- E["Sin imports absolutos a otros paquetes de dominio detectados"]']
    lines += ['```', '', f'Flujos transversales: [flujo actualizado]({rel("docs/BACKEND_CURRENT_FLOW.md")}).',
              '', 'Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.',
              'Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.', END]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    rows, stale = [], []
    for readme in sorted(ROOT.rglob('README.md')):
        relative = readme.relative_to(ROOT)
        if relative.parts[0] not in DOMAINS:
            continue
        text = readme.read_text(encoding='utf-8-sig')
        section = module_section(readme)
        original = text
        if START in text:
            before, rest = text.split(START, 1)
            _, after = rest.split(END, 1)
            text = before + section + after
        else:
            text = text.rstrip() + '\n\n' + section + '\n'
        if text != original:
            stale.append(relative.as_posix())
            if args.write:
                readme.write_text(text, encoding='utf-8', newline='\n')
        rows.append(f'| [{relative.parent.as_posix()}](../{relative.as_posix()}) | {len(sources(readme.parent))} | {text.count("```mermaid")} |')
    report = '\n'.join([
        '# Inventario documental del backend', '',
        'Generado desde el codigo del checkout; regenerar con `scripts/audit_backend_docs.py`.',
        'Se revisa el alcance de cada README de dominio, incluidos submodulos.',
        'Un diagrama de imports es evidencia estructural; el flujo de negocio se explica en',
        '[BACKEND_CURRENT_FLOW.md](BACKEND_CURRENT_FLOW.md).', '',
        f'README de dominio inventariados: **{len(rows)}**.', '',
        '| Modulo | Archivos de implementacion | Diagramas Mermaid |', '| --- | ---: | ---: |',
        *rows, '', '## Archivos que requieren revision', '',
        *[f'- `{p}`: {message}.' for p, message in sorted(PARSE_ERRORS.items())],
        *([] if PARSE_ERRORS else ['Sin errores de sintaxis detectados en las fuentes inventariadas.']),
        '', '## Catalogos ejecutables', '',
        '- Outboxes: ' + ', '.join(f'`{k}`' for k in keys('tasks/outbox_registry.py', 'OUTBOX_SPECS')) + '.',
        '- Workers: ' + ', '.join(f'`{k}`' for k in keys('tasks/workers/management/commands/run_worker.py', 'WORKER_COMMANDS')) + '.',
        '- Jobs: ' + ', '.join(f'`{k}`' for k in keys('tasks/scheduled/registry.py', 'SCHEDULED_JOBS')) + '.', '',
        '## Limites de la auditoria', '',
        'El analisis AST no importa Django ni lee archivos .env. No verifica callbacks externos,',
        'renderizado Mermaid, estado de PostgreSQL ni disponibilidad cloud. Los imports relativos,',
        'acciones dinamicas de DRF y modelos con bases no convencionales requieren lectura contextual.',
        'La narrativa historica no se considera certificada por la huella del inventario.', '',
    ])
    output = ROOT / 'docs/BACKEND_DOCUMENTATION_AUDIT.md'
    if not output.exists() or output.read_text(encoding='utf-8') != report:
        stale.append(output.relative_to(ROOT).as_posix())
        if args.write:
            output.write_text(report, encoding='utf-8', newline='\n')
    print(f'{len(rows)} READMEs audited; {len(stale)} files requiring refresh.')
    if args.check and stale:
        print('\n'.join(stale))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
