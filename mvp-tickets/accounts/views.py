"""
===============================================================================
Propósito:
    Vistas server-rendered para administrar usuarios, roles y permisos
    utilizando la UI basada en plantillas.
API pública:
    Vistas ``users_list``, ``user_create``, ``user_edit``, ``user_toggle`` y
    CRUD de roles consumidas en ``helpdesk/urls.py``.
Flujo de datos:
    Request autenticada → validación de permisos → formularios → operaciones
    ORM → respuestas HTML.
Dependencias:
    ``django.contrib.auth``, ``accounts.forms``, ``accounts.roles`` y
    ``accounts.permissions``.
Decisiones:
    Uso de helpers privados para construir plantillas de permisos y reducir
    duplicidad entre creación/edición de roles.
TODOs:
    TODO:PREGUNTA Evaluar si debe agregarse paginación server-side a los
    listados de usuarios cuando la base crezca.
===============================================================================
"""

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
import json
from typing import Any

from django.template.response import TemplateResponse
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group
from django.db.models import ProtectedError

from .forms import UserCreateForm, UserEditForm, RoleForm
from accounts.permissions import PERMISSION_TEMPLATES

User = get_user_model()


def _build_permission_templates(form: RoleForm) -> list[dict[str, Any]]:
    """Construye payload (id de permisos) para las plantillas rápidas de roles.

    Se traduce el catálogo declarativo de ``PERMISSION_TEMPLATES`` a la lista
    de IDs actual del formulario para asegurar que las plantillas reflejen el
    estado real de la base de datos y evitar referencias rotas.
    """

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
    """Contexto común para crear/editar roles con plantillas predefinidas.

    Devuelve estructura apta para la plantilla, incluyendo serialización JSON
    para el componente HTMX que sugiere permisos. Se agrega ``selected_permissions``
    para facilitar la rehidratación del formulario cuando hay errores.
    """

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
    """Listado de usuarios con filtros de texto, estado y grupo.

    Restringe acceso a usuarios con permiso ``auth.view_user`` y muestra un
    mensaje de error en caso contrario. El filtrado se realiza sobre campos
    básicos y utiliza ``order_by`` estable para mantener consistencia en la
    paginación manual.
    """
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
    """Crear nuevo usuario.

    Cuando la creación es exitosa se fuerza ``is_active`` según lo entregado en
    el formulario y se llama ``set_password`` para asegurar hashing. Los grupos
    se guardan con ``save_m2m`` para evitar referencias incompletas.
    """
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
    """Editar usuario existente, permitiendo cambio de password opcional.

    Se usa ``commit=False`` para interceptar la instancia y aplicar ``set_password``
    solo si se entregó un nuevo secreto. Caso contrario, se preserva el hash
    existente y se guardan relaciones muchas-a-muchas.
    """
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
    """Activar/Desactivar usuario.

    Invierte ``is_active`` y guarda solo ese campo para minimizar escritura. Se
    notifica al usuario mediante ``messages`` para mantener trazabilidad de la
    acción en la interfaz.
    """
    if not request.user.has_perm("auth.change_user"):
        messages.error(request, "No tienes permiso para cambiar el estado de un usuario.")
        return redirect("tickets_home")

    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"Usuario '{user.username}' → {'ACTIVO' if user.is_active else 'INACTIVO'}.")
    return redirect("accounts:users_list")


@login_required
def user_delete(request, pk):
    """Eliminar definitivamente un usuario existente."""

    if not request.user.has_perm("auth.delete_user"):
        messages.error(request, "No tienes permiso para eliminar usuarios.")
        return redirect("tickets_home")

    user = get_object_or_404(User, pk=pk)

    if request.method != "POST":
        return redirect("accounts:users_list")

    if user == request.user:
        messages.error(request, "No puedes eliminar tu propia cuenta mientras estás autenticado.")
        return redirect("accounts:users_list")

    username = user.username
    try:
        user.delete()
    except ProtectedError:
        messages.error(
            request,
            f"No se puede eliminar el usuario '{username}' porque tiene registros protegidos asociados.",
        )
    else:
        messages.success(request, f"Usuario '{username}' eliminado.")
    return redirect("accounts:users_list")


@login_required
def roles_list(request):
    """Listado de roles disponibles ordenados alfabéticamente.

    Solo accesible para usuarios con permiso ``auth.view_group``. Se centraliza
    el orden para que la UI mantenga un resultado determinista.
    """
    if not request.user.has_perm("auth.view_group"):
        messages.error(request, "No tienes permiso para ver los roles.")
        return redirect("tickets_home")

    roles = Group.objects.all().order_by("name")
    return TemplateResponse(request, "accounts/roles_list.html", {"roles": roles})


@login_required
def role_create(request):
    """Crear rol y asignar permisos.

    Utiliza ``RoleForm`` para validar combinaciones de permisos y muestra las
    plantillas predefinidas construidas por ``_role_form_context``. Los errores
    vuelven a la misma plantilla preservando selección del usuario.
    """
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
    """Editar rol y sus permisos manteniendo consistencia con el formulario.

    Se carga el objeto existente y se confía en las validaciones de ``RoleForm``
    para prevenir la eliminación accidental de permisos críticos.
    """
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


@login_required
def role_delete(request, pk):
    """Eliminar un rol cuando no tiene usuarios asociados."""

    if not request.user.has_perm("auth.delete_group"):
        messages.error(request, "No tienes permiso para eliminar roles.")
        return redirect("tickets_home")

    role = get_object_or_404(Group, pk=pk)

    if request.method != "POST":
        return redirect("accounts:roles_list")

    name = role.name
    if role.user_set.exists():
        messages.error(
            request,
            f"No se puede eliminar el rol '{name}' porque aún tiene usuarios asignados.",
        )
        return redirect("accounts:roles_list")

    try:
        role.delete()
    except ProtectedError:
        messages.error(
            request,
            f"No se puede eliminar el rol '{name}' porque está protegido por otros registros.",
        )
    else:
        messages.success(request, f"Rol '{name}' eliminado.")
    return redirect("accounts:roles_list")


@login_required
def password_change(request):
    """Permitir que cualquier usuario actualice su contraseña aplicando validadores."""

    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Tu contraseña se actualizó correctamente.")
            return redirect("account_password_change")
        messages.error(request, "Corrige los errores antes de continuar.")
    else:
        form = PasswordChangeForm(user=request.user)

    return TemplateResponse(request, "accounts/password_change.html", {"form": form})




