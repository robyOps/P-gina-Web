# catalog/forms.py
from django import forms

from .models import Category, Priority, Area

class CategoryForm(forms.ModelForm):
    """Formulario para crear y editar categorías."""

    class Meta:
        model = Category
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original_name = ""
        if self.instance and self.instance.pk and self.instance.name:
            original_name = self.instance.name
        self.fields["name"].widget.attrs.setdefault("data-original-name", original_name)

    def clean_name(self):
        """Evita nombres duplicados ignorando mayúsculas/minúsculas."""

        name = self.cleaned_data.get("name", "")
        normalized = name.strip()
        if not normalized:
            return normalized

        lookup = Category.objects.all()
        if self.instance and self.instance.pk:
            lookup = lookup.exclude(pk=self.instance.pk)

        if lookup.filter(name__iexact=normalized).exists():
            raise forms.ValidationError("Ya existe una categoría con este nombre.")

        return normalized

class PriorityForm(forms.ModelForm):
    class Meta:
        model = Priority
        fields = ["name", "sla_hours"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Alta"}),
            "sla_hours": forms.NumberInput(attrs={"min": 1}),
        }

class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ["name"]


