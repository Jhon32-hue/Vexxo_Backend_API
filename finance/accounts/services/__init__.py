"""
Paquete de servicios del bounded context `accounts`.

Descripcion general:
- agrupa casos de uso y adaptadores operativos del modulo

Analisis detallado:
- este paquete evita reexports pesados para no introducir ciclos de imports
- los consumidores deben importar el modulo concreto que necesiten
"""

__all__: list[str] = []
