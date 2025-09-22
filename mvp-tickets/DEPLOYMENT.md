# Guía de despliegue

Tras aplicar esta actualización es necesario ejecutar el refresco de permisos del sistema. Una vez desplegado el código en el servidor, corre el comando:

```bash
python manage.py migrate
```

Esto asegura que la migración que consolida los permisos del grupo `TECNICO` se aplique en entornos existentes.
