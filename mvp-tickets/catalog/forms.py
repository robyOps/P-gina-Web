# catalog/forms.py
from django import forms

from .models import Category, Priority, Area, Subcategory

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
        fields = ["name", "is_critical"]
        widgets = {
            "is_critical": forms.CheckboxInput(
                attrs={"class": "h-5 w-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"}
            )
        }


class SubcategoryForm(forms.ModelForm):
    class Meta:
        model = Subcategory
        fields = ["category", "name", "description", "is_active"]
        widgets = {
            "category": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "name": forms.TextInput(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "description": forms.Textarea(
                attrs={"class": "border rounded px-3 py-2 w-full", "rows": 3},
            ),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            return name
        return name.upper()

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        subcategory = cleaned.get("name")
        if category and subcategory:
            exists = Subcategory.objects.filter(
                category=category,
                name__iexact=subcategory.strip(),
            )
            if self.instance and self.instance.pk:
                exists = exists.exclude(pk=self.instance.pk)
            if exists.exists():
                self.add_error("name", "Ya existe una subcategoría con ese nombre en la categoría seleccionada.")
        return cleaned


