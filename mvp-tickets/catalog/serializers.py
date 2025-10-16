from rest_framework import serializers

from .models import Category, Priority, Area, Subcategory


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


class SubcategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Subcategory
        fields = ["id", "category", "category_name", "name", "description", "is_active"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        category = attrs.get("category") or getattr(self.instance, "category", None)
        name = attrs.get("name") or getattr(self.instance, "name", "")
        if category and name:
            lookup = Subcategory.objects.filter(category=category, name__iexact=name)
            if self.instance and self.instance.pk:
                lookup = lookup.exclude(pk=self.instance.pk)
            if lookup.exists():
                raise serializers.ValidationError(
                    {"name": "Ya existe una subcategoría con ese nombre en la categoría indicada."}
                )
        return attrs
