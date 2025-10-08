# MVP Tickets

Este repositorio contiene un ejemplo de mesa de ayuda construido con Django. El objetivo de esta rama es ofrecer un punto de partida limpio para continuar el desarrollo, sin archivos de pruebas residuales y con módulos documentados.

## Estructura

- `mvp-tickets/` proyecto Django principal con las apps `accounts`, `catalog`, `helpdesk`, `reports` y `tickets`.
- `templates/` archivos HTML base.
- `requirements.txt` dependencias mínimas para ejecutar el proyecto.

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Calidad del código

- Se eliminaron archivos de pruebas obsoletos (`tests.py`).
- Se refactorizaron las vistas del catálogo para reutilizar lógica y contar con comentarios descriptivos.
- Se documentaron los servicios de tickets para facilitar el mantenimiento.

Si vas a contribuir, sigue las convenciones existentes y agrega docstrings/comentarios claros cuando introduzcas nuevas piezas de negocio.
