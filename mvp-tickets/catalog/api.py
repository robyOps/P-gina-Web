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
    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return is_admin(request.user)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

class PriorityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Priority.objects.all()
    serializer_class = PrioritySerializer

class AreaViewSet(viewsets.ModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsAdminOrReadOnly]


class SubcategoryViewSet(viewsets.ModelViewSet):
    queryset = Subcategory.objects.select_related("category").all()
    serializer_class = SubcategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
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
