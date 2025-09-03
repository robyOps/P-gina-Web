# catalog/forms.py
from django import forms
from .models import Category, Priority, Area

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]

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


