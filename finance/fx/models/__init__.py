"""
Exports publicos del modulo de modelos FX.

Descripcion general:
- expone el catalogo de monedas y el modelo canonico de tasas
- mantiene compatibilidad hacia atras para imports antiguos
"""

from .fx import Currency, ExchangeRate, ExchangeRateProvider

FXRate = ExchangeRate

__all__ = [
    "Currency",
    "ExchangeRate",
    "ExchangeRateProvider",
    "FXRate",
]
