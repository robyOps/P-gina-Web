# tickets/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from accounts.roles import ROLE_ADMIN, ROLE_TECH
from .models import Ticket, AutoAssignRule, FAQ

User = get_user_model()

class TicketCreateForm(forms.ModelForm):
    """
    Form para crear ticket. Si el usuario es ADMINISTRADOR, se muestra un campo
    opcional 'assignee' para asignar a un técnico desde la creación.
    """
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Asignar a",
        widget=forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"})
    )

    class Meta:
        model = Ticket
        fields = ("title", "description", "category", "priority", "area", "kind")
        widgets = {
            "title": forms.TextInput(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "description": forms.Textarea(attrs={"class": "border rounded px-3 py-2 w-full", "rows": 4}),
            "category": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "priority": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "area": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "kind": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Solo ADMINISTRADOR ve y puede usar el campo para asignar
        if user and (user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists()):
            try:
                tech_group = Group.objects.get(name=ROLE_TECH)
                self.fields["assignee"].queryset = (
                    User.objects.filter(groups=tech_group, is_active=True)
                    .order_by("username")
                )
            except Group.DoesNotExist:
                self.fields["assignee"].queryset = User.objects.none()
        else:
            # Usuarios no admin: no mostramos el campo
            self.fields.pop("assignee", None)


class AutoAssignRuleForm(forms.ModelForm):
    class Meta:
        model = AutoAssignRule
        fields = ["category", "area", "tech", "is_active"]
        widgets = {
            "category": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "area": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "tech": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            g = Group.objects.get(name=ROLE_TECH)
            self.fields["tech"].queryset = User.objects.filter(groups=g, is_active=True).order_by("username")
        except Group.DoesNotExist:
            self.fields["tech"].queryset = User.objects.none()
        self.fields["category"].required = False
        self.fields["area"].required = False


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer"]
        widgets = {
            "question": forms.TextInput(
                attrs={"class": "border rounded px-3 py-2 w-full", "maxlength": 255}
            ),
            "answer": forms.Textarea(
                attrs={"class": "border rounded px-3 py-2 w-full", "rows": 4}
            ),
        }
