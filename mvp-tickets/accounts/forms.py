"""
===============================================================================
Propósito:
    Formularios de administración para crear/editar usuarios y roles.
API pública:
    ``UserCreateForm``, ``UserEditForm`` y ``RoleForm`` consumidos por vistas en
    ``accounts.views``.
Flujo de datos:
    Datos HTML → validaciones de formulario → instancias de modelos → guardado
    mediante ``ModelForm``.
Dependencias:
    ``django.contrib.auth`` para modelos de usuario/grupo y permisos definidos en
    ``accounts.permissions``.
Decisiones:
    Se reutiliza `ModelMultipleChoiceField` con etiquetas personalizadas para
    mejorar la usabilidad de selección de permisos.
TODOs:
    TODO:PREGUNTA Determinar reglas adicionales de complejidad de contraseña que
    deban aplicarse en formularios.
===============================================================================
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from .permissions import PERMISSION_LABELS, group_permissions

User = get_user_model()


class UserCreateForm(forms.ModelForm):
    """Formulario para alta de usuarios con validación de contraseñas coincidentes."""

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
        """Valida que las contraseñas ingresadas coincidan antes de guardar."""

        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned


class UserEditForm(forms.ModelForm):
    """Formulario de edición que permite cambiar contraseña de forma opcional."""

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
        """Verifica que las contraseñas nuevas coincidan solo si fueron provistas."""

        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if (p1 or p2) and p1 != p2:
            self.add_error("new_password2", "Las contraseñas no coinciden.")
        return cleaned


class RoleForm(forms.ModelForm):
    """Formulario para crear/editar roles controlando visualmente los permisos."""

    permissions = forms.ModelMultipleChoiceField(
        label="Permisos",
        queryset=Permission.objects.filter(
            codename__in=PERMISSION_LABELS.keys()
        ).order_by("content_type__app_label", "codename"),
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "class": "permission-grid grid sm:grid-cols-2 gap-3 list-none max-h-96 overflow-y-auto p-3 border border-gray-200 rounded-lg bg-white/60",
            }
        ),
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        labels = {"name": "Nombre"}

    def __init__(self, *args, **kwargs):
        """Configura etiquetas amigables y agrupa permisos para la plantilla."""

        super().__init__(*args, **kwargs)

        def label_from_instance(obj):
            return PERMISSION_LABELS.get(obj.codename, obj.name)

        self.fields["permissions"].label_from_instance = label_from_instance
        self.permission_groups = group_permissions(self.fields["permissions"].queryset)
