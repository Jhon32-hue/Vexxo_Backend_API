# API throttling

DRF aplica limites globales:

- anonimo: 100 requests por hora
- autenticado: 2.000 requests por hora

El permiso global es `IsAuthenticated`. Cada endpoint realmente publico debe
declarar `AllowAny` de forma explicita.

Estos limites no sustituyen scopes especificos para login, recuperacion,
intake, pagos o callbacks. Deben agregarse antes de exponer el sistema.
