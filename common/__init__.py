"""
Paquete ``common``.

Este modulo expone utilidades compartidas entre dominios, pero no debe importar
views, URLs ni componentes de Django REST Framework en tiempo de import del
paquete. Eso se resuelve desde ``common.urls`` o ``common.views`` cuando hace
falta, no desde ``common.__init__``.
"""
