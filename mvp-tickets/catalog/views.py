"""Vistas del catálogo de tickets."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse


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
# ---------------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------------
@login_required
@permission_required("catalog.view_category", raise_exception=True)
def categories_list(request):
    """Lista todas las categorías ordenadas alfabéticamente."""

    qs = Category.objects.all().order_by("name")
    return TemplateResponse(request, "catalog/categories_list.html", {"items": qs})


@login_required
@permission_required("catalog.add_category", raise_exception=True)
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
@permission_required("catalog.change_category", raise_exception=True)
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
@permission_required("catalog.view_priority", raise_exception=True)
def priorities_list(request):
    """Lista las prioridades disponibles. Solo para administradores."""

    qs = Priority.objects.all().order_by("name")
    return render(request, "catalog/priorities_list.html", {"rows": qs})


@login_required
@permission_required("catalog.add_priority", raise_exception=True)
def priority_create(request):
    """Crea una nueva prioridad."""

    return _handle_simple_form(
        request,
        form_class=PriorityForm,
        template_name="catalog/priority_form.html",
        redirect_url="priorities_list",
        success_message="Prioridad creada.",
    )


@login_required
@permission_required("catalog.change_priority", raise_exception=True)
def priority_edit(request, pk):
    """Permite editar una prioridad existente."""

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
@permission_required("catalog.view_area", raise_exception=True)
def areas_list(request):
    """Lista las áreas registradas."""

    qs = Area.objects.all().order_by("name")
    return TemplateResponse(request, "catalog/areas_list.html", {"items": qs})


@login_required
@permission_required("catalog.add_area", raise_exception=True)
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
@permission_required("catalog.change_area", raise_exception=True)
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

