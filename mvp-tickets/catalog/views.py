"""Vistas del catálogo de tickets."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse

from accounts.roles import ROLE_ADMIN, is_admin

from .forms import AreaForm, CategoryForm, PriorityForm
from .models import Area, Category, Priority


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _handle_simple_form(
    request,
    *,
    form_class,
    template_name: str,
    redirect_url: str,
    success_message: str,
    instance=None,
    extra_context: dict | None = None,
):
    """Gestiona el ciclo común de creación/edición para formularios sencillos."""

    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, success_message)
            return redirect(redirect_url)
        messages.error(request, "Revisa los campos.")
    else:
        form = form_class(instance=instance)

    context = {"form": form, "is_new": instance is None}
    if instance:
        context["obj"] = instance
    if extra_context:
        context.update(extra_context)

    return TemplateResponse(request, template_name, context)


def _ensure_admin(user):
    """Devuelve None si el usuario es admin o una respuesta 403 en otro caso."""

    if is_admin(user):
        return None
    return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")


# ---------------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------------
@login_required
@user_passes_test(is_admin)
def categories_list(request):
    """Lista todas las categorías ordenadas alfabéticamente."""

    qs = Category.objects.all().order_by("name")
    return TemplateResponse(request, "catalog/categories_list.html", {"items": qs})


@login_required
@user_passes_test(is_admin)
def category_create(request):
    """Crea una nueva categoría."""

    return _handle_simple_form(
        request,
        form_class=CategoryForm,
        template_name="catalog/category_form.html",
        redirect_url="categories_list",
        success_message="Categoría creada.",
    )


@login_required
@user_passes_test(is_admin)
def category_edit(request, pk):
    """Edita la categoría seleccionada."""

    obj = get_object_or_404(Category, pk=pk)
    return _handle_simple_form(
        request,
        form_class=CategoryForm,
        template_name="catalog/category_form.html",
        redirect_url="categories_list",
        success_message="Categoría actualizada.",
        instance=obj,
    )


# ---------------------------------------------------------------------------
# Prioridades
# ---------------------------------------------------------------------------
@login_required
def priorities_list(request):
    """Lista las prioridades disponibles. Solo para administradores."""

    forbidden = _ensure_admin(request.user)
    if forbidden:
        return forbidden

    qs = Priority.objects.all().order_by("name")
    return render(request, "catalog/priorities_list.html", {"rows": qs})


@login_required
def priority_create(request):
    """Crea una nueva prioridad."""

    forbidden = _ensure_admin(request.user)
    if forbidden:
        return forbidden

    return _handle_simple_form(
        request,
        form_class=PriorityForm,
        template_name="catalog/priority_form.html",
        redirect_url="priorities_list",
        success_message="Prioridad creada.",
    )


@login_required
def priority_edit(request, pk):
    """Permite editar una prioridad existente."""

    forbidden = _ensure_admin(request.user)
    if forbidden:
        return forbidden

    obj = get_object_or_404(Priority, pk=pk)
    return _handle_simple_form(
        request,
        form_class=PriorityForm,
        template_name="catalog/priority_form.html",
        redirect_url="priorities_list",
        success_message="Prioridad actualizada.",
        instance=obj,
    )


# ---------------------------------------------------------------------------
# Áreas
# ---------------------------------------------------------------------------
@login_required
@user_passes_test(is_admin)
def areas_list(request):
    """Lista las áreas registradas."""

    qs = Area.objects.all().order_by("name")
    return TemplateResponse(request, "catalog/areas_list.html", {"items": qs})


@login_required
@user_passes_test(is_admin)
def area_create(request):
    """Crea un área nueva."""

    return _handle_simple_form(
        request,
        form_class=AreaForm,
        template_name="catalog/area_form.html",
        redirect_url="areas_list",
        success_message="Área creada.",
    )


@login_required
@user_passes_test(is_admin)
def area_edit(request, pk):
    """Edita un área existente."""

    obj = get_object_or_404(Area, pk=pk)
    return _handle_simple_form(
        request,
        form_class=AreaForm,
        template_name="catalog/area_form.html",
        redirect_url="areas_list",
        success_message="Área actualizada.",
        instance=obj,
    )

