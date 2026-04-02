"""
Entradas HTTP futuras para `payments.payment_intents`.

Por ahora el modulo se usa principalmente via servicios internos:
- `create_payment_intent(...)`
- callbacks internos o workers que cambian estado del intent

Cuando se exponga API, aqui deben vivir:
- create intent
- confirm / cancel
- callback interno autenticado desde integradores o workers
"""
