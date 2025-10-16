# tickets/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from accounts.roles import ROLE_ADMIN, ROLE_TECH
from .models import Ticket, AutoAssignRule, FAQ
from catalog.models import Category, Priority, Area, Subcategory
from .utils import sanitize_text

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
        fields = ("title", "description", "category", "subcategory", "priority", "area", "kind")
        widgets = {
            "title": forms.TextInput(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "description": forms.Textarea(attrs={"class": "border rounded px-3 py-2 w-full", "rows": 4}),
            "category": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "subcategory": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "priority": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "area": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "kind": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        self.fields["priority"].queryset = Priority.objects.order_by("sla_hours", "name")

        subcategory_qs = Subcategory.objects.select_related("category").filter(is_active=True)
        self.fields["subcategory"].queryset = subcategory_qs.order_by("category__name", "name")
        self.fields["subcategory"].required = False
        self.fields["subcategory"].empty_label = "Sin subcategoría"

        self._default_category = self.fields["category"].queryset.first()
        self._default_priority = self.fields["priority"].queryset.first()

        self._can_choose_category = bool(
            user and user.has_perm("tickets.set_ticket_category")
        )
        self._can_choose_priority = bool(
            user and user.has_perm("tickets.set_ticket_priority")
        )

        if not self._can_choose_category:
            if self._default_category:
                self.fields["category"].initial = self._default_category.pk
            self.fields["category"].widget = forms.HiddenInput()
            self.fields["subcategory"].widget = forms.HiddenInput()

        if not self._can_choose_priority:
            if self._default_priority:
                self.fields["priority"].initial = self._default_priority.pk
            self.fields["priority"].widget = forms.HiddenInput()

        is_admin_user = bool(user and (user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists()))

        if is_admin_user:
            try:
                tech_group = Group.objects.get(name=ROLE_TECH)
                self.fields["assignee"].queryset = (
                    User.objects.filter(groups=tech_group, is_active=True)
                    .order_by("username")
                )
            except Group.DoesNotExist:
                self.fields["assignee"].queryset = User.objects.none()
        else:
            # Usuarios no admin: ocultamos asignación manual
            self.fields.pop("assignee", None)
            if self._can_choose_category and self._default_category:
                self.fields["category"].initial = self._default_category.pk
            if self._can_choose_priority and self._default_priority:
                self.fields["priority"].initial = self._default_priority.pk

    def clean_title(self):
        title = sanitize_text(self.cleaned_data.get("title"))
        if not title:
            raise forms.ValidationError("El título es obligatorio.")
        return title

    def clean_description(self):
        description = sanitize_text(self.cleaned_data.get("description"))
        if not description:
            raise forms.ValidationError("La descripción es obligatoria.")
        return description

    def clean_category(self):
        if not self._can_choose_category:
            if self._default_category:
                return self._default_category
            raise forms.ValidationError(
                "No hay categorías disponibles. Contacta al administrador."
            )

        category = self.cleaned_data.get("category")
        if category:
            return category
        if self._default_category:
            return self._default_category
        raise forms.ValidationError("No hay categorías disponibles. Contacta al administrador.")

    def clean_subcategory(self):
        if not self._can_choose_category:
            return None

        category = self.cleaned_data.get("category") or self._default_category
        subcategory = self.cleaned_data.get("subcategory")
        if not subcategory:
            return None
        if category and subcategory.category_id != category.id:
            raise forms.ValidationError("La subcategoría no pertenece a la categoría seleccionada.")
        return subcategory

    def clean_priority(self):
        if not self._can_choose_priority:
            if self._default_priority:
                return self._default_priority
            raise forms.ValidationError(
                "No hay prioridades disponibles. Contacta al administrador."
            )

        priority = self.cleaned_data.get("priority")
        if priority:
            return priority
        if self._default_priority:
            return self._default_priority
        raise forms.ValidationError("No hay prioridades disponibles. Contacta al administrador.")


class TicketQuickUpdateForm(forms.ModelForm):
    """Formulario compacto para actualizar campos principales de un ticket."""

    class Meta:
        model = Ticket
        fields = ("title", "category", "subcategory", "priority", "area", "kind")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-3 py-2 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100",
                    "placeholder": "Resumen del ticket",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-3 py-2 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100",
                }
            ),
            "subcategory": forms.Select(
                attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-3 py-2 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100",
                }
            ),
            "priority": forms.Select(
                attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-3 py-2 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100",
                }
            ),
            "area": forms.Select(
                attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-3 py-2 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100",
                }
            ),
            "kind": forms.Select(
                attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-3 py-2 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self._user = user
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("name")
        subcategory_qs = Subcategory.objects.select_related("category").order_by("category__name", "name")
        self.fields["subcategory"].queryset = subcategory_qs
        self.fields["priority"].queryset = Priority.objects.order_by("name")
        self.fields["area"].queryset = Area.objects.order_by("name")
        self.fields["area"].required = False
        self.fields["area"].empty_label = "Sin área"
        self.fields["subcategory"].required = False
        self.fields["subcategory"].empty_label = "Sin subcategoría"

        self._can_choose_category = bool(
            user and user.has_perm("tickets.set_ticket_category")
        )
        self._can_choose_priority = bool(
            user and user.has_perm("tickets.set_ticket_priority")
        )

        if not self._can_choose_category:
            self.fields["category"].widget = forms.HiddenInput()
            self.fields["subcategory"].widget = forms.HiddenInput()

        if not self._can_choose_priority:
            self.fields["priority"].widget = forms.HiddenInput()

    def clean_title(self):
        title = sanitize_text(self.cleaned_data.get("title"))
        if not title:
            raise forms.ValidationError("El título es obligatorio.")
        return title

    def clean_category(self):
        if not self._can_choose_category:
            return self.instance.category
        category = self.cleaned_data.get("category")
        if category:
            return category
        raise forms.ValidationError("La categoría es obligatoria.")

    def clean_subcategory(self):
        if not self._can_choose_category:
            return getattr(self.instance, "subcategory", None)

        category = self.cleaned_data.get("category")
        subcategory = self.cleaned_data.get("subcategory")
        if not subcategory:
            return None
        if category and subcategory.category_id != category.id:
            raise forms.ValidationError("La subcategoría no pertenece a la categoría seleccionada.")
        return subcategory

    def clean_priority(self):
        if not self._can_choose_priority:
            return self.instance.priority
        priority = self.cleaned_data.get("priority")
        if priority:
            return priority
        raise forms.ValidationError("La prioridad es obligatoria.")

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
        fields = ["question", "answer", "category", "subcategory"]
        widgets = {
            "question": forms.TextInput(
                attrs={"class": "border rounded px-3 py-2 w-full", "maxlength": 255}
            ),
            "answer": forms.Textarea(
                attrs={"class": "border rounded px-3 py-2 w-full", "rows": 4}
            ),
            "category": forms.Select(
                attrs={"class": "border rounded px-3 py-2 w-full"}
            ),
            "subcategory": forms.Select(
                attrs={"class": "border rounded px-3 py-2 w-full"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["category"].required = False
        self.fields["category"].empty_label = "Sin categoría"
        self.fields["subcategory"].queryset = Subcategory.objects.select_related("category").order_by("category__name", "name")
        self.fields["subcategory"].required = False
        self.fields["subcategory"].empty_label = "Sin subcategoría"

    def clean_question(self):
        question = sanitize_text(self.cleaned_data.get("question"))
        if not question:
            raise forms.ValidationError("La pregunta no puede estar vacía.")
        return question

    def clean_answer(self):
        answer = sanitize_text(self.cleaned_data.get("answer"))
        if not answer:
            raise forms.ValidationError("La respuesta no puede estar vacía.")
        return answer

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        subcategory = cleaned.get("subcategory")
        if subcategory:
            if category and subcategory.category_id != category.id:
                self.add_error(
                    "subcategory",
                    "La subcategoría seleccionada no pertenece a la categoría indicada.",
                )
            elif not category:
                cleaned["category"] = subcategory.category
        return cleaned
