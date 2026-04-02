"""
El bounded context de `payment_intents` prioriza servicios canónicos.

Las transiciones operativas deben pasar por `payments.payment_intents.services`
para:
- aplicar guards de producto
- calcular pricing
- publicar eventos `payments.*`
- materializar ledger cuando corresponda

Este modulo se mantiene intencionalmente liviano para no duplicar side effects
entre services y model signals.
"""
