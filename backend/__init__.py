"""
Paquete principal del proyecto backend.

Este archivo debe mantenerse sin imports que inicialicen Django, WSGI o ASGI.
La carga temprana de ``get_wsgi_application()`` o imports de apps aquí rompe
el arranque del registry durante comandos como ``manage.py check`` y tests.
"""
