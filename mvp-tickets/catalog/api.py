"""
===============================================================================
Propósito:
    Exponer CRUD del catálogo mediante viewsets de Django REST Framework.
API pública:
    ``CategoryViewSet``, ``PriorityViewSet``, ``AreaViewSet`` y
    ``SubcategoryViewSet`` registrados en ``helpdesk/api_urls.py``.
Flujo de datos:
    Request REST → permisos → queryset → serializador → respuesta JSON.
Dependencias:
    Modelos y serializadores del catálogo, además de helpers de roles.
Decisiones:
    Se restringen operaciones de escritura a administradores reutilizando
    ``IsAdminOrReadOnly``.
TODOs:
    TODO:PREGUNTA Definir si los técnicos pueden crear subcategorías temporales
    desde la API.
===============================================================================
"""

from rest_framework import viewsets, permissions
from .models import Category, Priority, Area, Subcategory
from .serializers import (
    CategorySerializer,
    PrioritySerializer,
    AreaSerializer,
    SubcategorySerializer,
)
from accounts.roles import is_admin


class IsAdminOrReadOnly(permissions.BasePermission):
    """Permite lectura a cualquiera autenticado y escritura solo a administradores."""

    def has_permission(self, request, view):
        """Evalúa método HTTP y pertenencia al grupo administrador."""

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return is_admin(request.user)


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD completo de categorías con permisos de administrador para escritura."""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class PriorityViewSet(viewsets.ReadOnlyModelViewSet):
    """Exposición solo-lectura de prioridades para clientes y formularios."""

    queryset = Priority.objects.all()
    serializer_class = PrioritySerializer


class AreaViewSet(viewsets.ModelViewSet):
    """CRUD de áreas responsables restringido a administradores."""

    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsAdminOrReadOnly]


class SubcategoryViewSet(viewsets.ModelViewSet):
    """CRUD de subcategorías con filtro opcional por categoría."""

    queryset = Subcategory.objects.select_related("category").all()
    serializer_class = SubcategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        """Permite filtrar por categoría usando ID o nombre insensible a mayúsculas."""

        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            try:
                category_id = int(category)
            except (TypeError, ValueError):
                category_id = None
            if category_id:
                qs = qs.filter(category_id=category_id)
            else:
                qs = qs.filter(category__name__iexact=category)
        return qs
