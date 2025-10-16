from rest_framework import serializers

from .models import Category, Priority, Area


class CategorySerializer(serializers.ModelSerializer):
    """Serializador para exponer y crear categorías."""

    class Meta:
        model = Category
        fields = "__all__"

    def validate_name(self, value: str) -> str:
        """Valida que el nombre sea único sin importar mayúsculas/minúsculas."""

        normalized = (value or "").strip()
        if not normalized:
            return normalized

        queryset = Category.objects.all()
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.filter(name__iexact=normalized).exists():
            raise serializers.ValidationError("Ya existe una categoría con este nombre.")

        return normalized


class PrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Priority
        fields = "__all__"


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = "__all__"
