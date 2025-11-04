"""Vistas del catálogo de tickets."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse


from .forms import AreaForm, CategoryForm, PriorityForm, SubcategoryForm
from .models import Area, Category, Priority, Subcategory


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
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, "Ya existe un registro con esos datos.")
                messages.error(request, "Ese registro ya existe. Intenta con otro nombre.")
            else:
                messages.success(request, success_message)
                return redirect(redirect_url)
        else:
            messages.error(request, "Revisa los campos.")
    else:
        form = form_class(instance=instance)

    context = {"form": form, "is_new": instance is None}
    if instance:
        context["obj"] = instance
    if extra_context:
        context.update(extra_context)

    return TemplateResponse(request, template_name, context)


def _handle_delete(
    request,
    *,
    obj,
    redirect_url: str,
    success_message: str,
):
    """Gestiona el ciclo de eliminación con manejo de errores protegidos."""

    if request.method != "POST":
        return redirect(redirect_url)

    name = str(obj)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(
            request,
            f"No se puede eliminar '{name}' porque otros registros todavía lo utilizan.",
        )
    else:
        messages.success(request, success_message.format(name=name))
    return redirect(redirect_url)
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
        extra_context={
            "existing_names": list(Category.objects.order_by("name").values_list("name", flat=True))
        },
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
        extra_context={
            "existing_names": list(
                Category.objects.exclude(pk=obj.pk).order_by("name").values_list("name", flat=True)
            )
        },
    )


@login_required
@permission_required("catalog.delete_category", raise_exception=True)
def category_delete(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    return _handle_delete(
        request,
        obj=obj,
        redirect_url="categories_list",
        success_message="Categoría '{name}' eliminada.",
    )


# ---------------------------------------------------------------------------
# Subcategorías
# ---------------------------------------------------------------------------
@login_required
@permission_required("catalog.view_subcategory", raise_exception=True)
def subcategories_list(request):
    items = (
        Subcategory.objects.select_related("category")
        .order_by("category__name", "name")
    )
    return TemplateResponse(request, "catalog/subcategories_list.html", {"items": items})


@login_required
@permission_required("catalog.add_subcategory", raise_exception=True)
def subcategory_create(request):
    return _handle_simple_form(
        request,
        form_class=SubcategoryForm,
        template_name="catalog/subcategory_form.html",
        redirect_url="subcategories_list",
        success_message="Subcategoría creada.",
    )


@login_required
@permission_required("catalog.change_subcategory", raise_exception=True)
def subcategory_edit(request, pk):
    obj = get_object_or_404(Subcategory, pk=pk)
    return _handle_simple_form(
        request,
        form_class=SubcategoryForm,
        template_name="catalog/subcategory_form.html",
        redirect_url="subcategories_list",
        success_message="Subcategoría actualizada.",
        instance=obj,
    )


@login_required
@permission_required("catalog.delete_subcategory", raise_exception=True)
def subcategory_delete(request, pk):
    obj = get_object_or_404(Subcategory, pk=pk)
    return _handle_delete(
        request,
        obj=obj,
        redirect_url="subcategories_list",
        success_message="Subcategoría '{name}' eliminada.",
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


@login_required
@permission_required("catalog.delete_priority", raise_exception=True)
def priority_delete(request, pk):
    obj = get_object_or_404(Priority, pk=pk)
    return _handle_delete(
        request,
        obj=obj,
        redirect_url="priorities_list",
        success_message="Prioridad '{name}' eliminada.",
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


@login_required
@permission_required("catalog.delete_area", raise_exception=True)
def area_delete(request, pk):
    obj = get_object_or_404(Area, pk=pk)
    return _handle_delete(
        request,
        obj=obj,
        redirect_url="areas_list",
        success_message="Área '{name}' eliminada.",
    )

