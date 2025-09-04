from rest_framework import viewsets, permissions
from .models import Category, Priority, Area
from .serializers import CategorySerializer, PrioritySerializer, AreaSerializer
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
