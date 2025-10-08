# accounts/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
import json
from typing import Any

from django.template.response import TemplateResponse
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .forms import UserCreateForm, UserEditForm, RoleForm
from accounts.permissions import PERMISSION_TEMPLATES

User = get_user_model()


def _build_permission_templates(form: RoleForm) -> list[dict[str, Any]]:
    """Construye payload (id de permisos) para las plantillas rápidas de roles."""

    available = form.fields["permissions"].queryset
    id_by_code = {p.codename: str(p.id) for p in available}
    templates: list[dict[str, Any]] = []
    for key, config in PERMISSION_TEMPLATES.items():
        codes = config.get("codenames", [])
        ids = [id_by_code[c] for c in codes if c in id_by_code]
        if not ids:
            continue
        template_key = str(key).lower()
        templates.append(
            {
                "key": template_key,
                "label": config.get("label", str(key)),
                "description": config.get("description", ""),
                "permission_ids": ids,
            }
        )
    templates.sort(key=lambda t: t["label"].lower())
    return templates


def _role_form_context(form: RoleForm, **extra) -> dict:
    """Contexto común para crear/editar roles con plantillas predefinidas."""

    permission_templates = _build_permission_templates(form)
    selected_permissions = {
        str(value)
        for value in (form["permissions"].value() or [])
    }
    ctx = {
        "form": form,
        "permission_templates": permission_templates,
        "permission_templates_json": json.dumps(permission_templates, ensure_ascii=False),
        "permission_groups": getattr(form, "permission_groups", []),
        "selected_permissions": selected_permissions,
    }
    ctx.update(extra)
    return ctx


@login_required
def users_list(request):
    """Listado de usuarios. Filtros básicos por texto, estado y grupo."""
    if not request.user.has_perm("auth.view_user"):
        messages.error(request, "No tienes permiso para ver usuarios.")
        return redirect("tickets_home")

    q = (request.GET.get("q") or "").strip()
    active = request.GET.get("active")  # "1" | "0" | ""
    g = request.GET.get("group")        # id de grupo

    users = User.objects.all().order_by("username")

    if q:
        users = users.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )
    if active in ("0", "1"):
        users = users.filter(is_active=(active == "1"))
    if g:
        users = users.filter(groups__id=g)

    groups = Group.objects.all().order_by("name")

    ctx = {
        "users": users,
        "groups": groups,
        "filters": {"q": q, "active": active, "group": g},
    }
    return TemplateResponse(request, "accounts/users_list.html", ctx)


@login_required
def user_create(request):
    """Crear nuevo usuario."""
    if not request.user.has_perm("auth.add_user"):
        messages.error(request, "No tienes permiso para crear usuarios.")
        return redirect("tickets_home")

    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = form.cleaned_data["is_active"]
            user.set_password(form.cleaned_data["password1"])
            user.save()
            form.save_m2m()  # asigna grupos

            messages.success(request, f"Usuario '{user.username}' creado.")
            return redirect("accounts:users_list")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = UserCreateForm()

    return TemplateResponse(request, "accounts/user_form.html", {"form": form, "is_new": True})


@login_required
def user_edit(request, pk):
    """Editar usuario."""
    if not request.user.has_perm("auth.change_user"):
        messages.error(request, "No tienes permiso para editar usuarios.")
        return redirect("tickets_home")

    user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            u = form.save(commit=False)
            p1 = form.cleaned_data.get("new_password1")
            if p1:
                u.set_password(p1)
            u.save()
            form.save_m2m()

            messages.success(request, f"Usuario '{u.username}' actualizado.")
            return redirect("accounts:users_list")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = UserEditForm(instance=user)

    return TemplateResponse(request, "accounts/user_form.html", {"form": form, "is_new": False, "obj": user})


@login_required
def user_toggle(request, pk):
    """Activar/Desactivar usuario."""
    if not request.user.has_perm("auth.change_user"):
        messages.error(request, "No tienes permiso para cambiar el estado de un usuario.")
        return redirect("tickets_home")

    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"Usuario '{user.username}' → {'ACTIVO' if user.is_active else 'INACTIVO'}.")
    return redirect("accounts:users_list")


@login_required
def roles_list(request):
    """Listado de roles disponibles."""
    if not request.user.has_perm("auth.view_group"):
        messages.error(request, "No tienes permiso para ver los roles.")
        return redirect("tickets_home")

    roles = Group.objects.all().order_by("name")
    return TemplateResponse(request, "accounts/roles_list.html", {"roles": roles})


@login_required
def role_create(request):
    """Crear rol y asignar permisos."""
    if not request.user.has_perm("auth.add_group"):
        messages.error(request, "No tienes permiso para crear roles.")
        return redirect("tickets_home")

    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Rol creado.")
            return redirect("accounts:roles_list")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = RoleForm()

    ctx = _role_form_context(form, is_new=True)
    return TemplateResponse(request, "accounts/role_form.html", ctx)


@login_required
def role_edit(request, pk):
    """Editar rol y sus permisos."""
    if not request.user.has_perm("auth.change_group"):
        messages.error(request, "No tienes permiso para editar roles.")
        return redirect("tickets_home")

    role = get_object_or_404(Group, pk=pk)

    if request.method == "POST":
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            messages.success(request, "Rol actualizado.")
            return redirect("accounts:roles_list")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = RoleForm(instance=role)

    ctx = _role_form_context(form, is_new=False, obj=role)
    return TemplateResponse(request, "accounts/role_form.html", ctx)




