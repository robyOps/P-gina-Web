# accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput, required=True)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput, required=True)
    groups = forms.ModelMultipleChoiceField(
        label="Grupos (roles)",
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    is_active = forms.BooleanField(label="Activo", required=False, initial=True)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "is_active", "groups"]

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned


class UserEditForm(forms.ModelForm):
    # Opcional: si rellenas, cambia la contraseña
    new_password1 = forms.CharField(label="Nueva contraseña", widget=forms.PasswordInput, required=False)
    new_password2 = forms.CharField(label="Repite la nueva contraseña", widget=forms.PasswordInput, required=False)
    groups = forms.ModelMultipleChoiceField(
        label="Grupos (roles)",
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    is_active = forms.BooleanField(label="Activo", required=False)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "is_active", "groups"]

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if (p1 or p2) and p1 != p2:
            self.add_error("new_password2", "Las contraseñas no coinciden.")
        return cleaned


