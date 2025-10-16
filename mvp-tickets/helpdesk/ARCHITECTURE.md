# Arquitectura de `helpdesk`

## Contexto
Módulo proyecto que concentra configuración global, enrutamiento HTTP y puntos de
entrada WSGI/ASGI.

## Componentes
- `settings.py`: configuración de Django, DRF y dependencias externas.
- `urls.py`: enrutamiento de vistas HTML y API principal.
- `api_urls.py`: registro de endpoints REST.
- `wsgi.py` y `asgi.py`: puertas de entrada para servidores.

## Contratos
- Expone `urlpatterns` y `router` consumidos por Django.
- Variables de entorno `TICKET_LABEL_SUGGESTION_THRESHOLD`, credenciales y
  configuración de CORS.

## Dependencias internas
- Apps `accounts`, `catalog`, `tickets`, `reports`.
- Plantillas HTML ubicadas en `templates/`.

## Diagrama ASCII
```
[Cliente HTTP]
      |
      v
 helpdesk.urls --include--> helpdesk.api_urls
      |                          |
      v                          v
  vistas tickets            APIs DRF
```

## Reglas de límites
- No realizar lógica de negocio aquí; delegar a apps hijas.
- Mantener configuraciones sensibles en variables de entorno.
- Evitar dependencias circulares con apps; únicamente importar vistas/routers.
