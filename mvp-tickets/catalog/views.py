# catalog/views.py
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.template.response import TemplateResponse

from .models import Category, Priority, Area
from .forms import CategoryForm, PriorityForm, AreaForm


from django.http import HttpResponseForbidden
from accounts.roles import is_admin, ROLE_ADMIN

# -------- Categorías --------
@login_required
@user_passes_test(is_admin)
def categories_list(request):
    qs = Category.objects.all().order_by("name")
    return TemplateResponse(request, "catalog/categories_list.html", {"items": qs})

@login_required
@user_passes_test(is_admin)
def category_create(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría creada.")
            return redirect("categories_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = CategoryForm()
    return TemplateResponse(request, "catalog/category_form.html", {"form": form, "is_new": True})

@login_required
@user_passes_test(is_admin)
def category_edit(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría actualizada.")
            return redirect("categories_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = CategoryForm(instance=obj)
    return TemplateResponse(request, "catalog/category_form.html", {"form": form, "is_new": False, "obj": obj})

# -------- Prioridades --------
@login_required
def priorities_list(request):
    if not is_admin(request.user):
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
    qs = Priority.objects.all().order_by("name")
    return render(request, "catalog/priorities_list.html", {"rows": qs})

@login_required
def priority_create(request):
    if not is_admin(request.user):
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
    if request.method == "POST":
        form = PriorityForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Prioridad creada.")
            return redirect("priorities_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = PriorityForm()
    return render(request, "catalog/priority_form.html", {"form": form, "is_new": True})

@login_required
def priority_edit(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
    obj = get_object_or_404(Priority, pk=pk)
    if request.method == "POST":
        form = PriorityForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Prioridad actualizada.")
            return redirect("priorities_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = PriorityForm(instance=obj)
    return render(request, "catalog/priority_form.html", {"form": form, "is_new": False, "obj": obj})

# -------- Áreas --------
@login_required
@user_passes_test(is_admin)
def areas_list(request):
    qs = Area.objects.all().order_by("name")
    return TemplateResponse(request, "catalog/areas_list.html", {"items": qs})

@login_required
@user_passes_test(is_admin)
def area_create(request):
    if request.method == "POST":
        form = AreaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Área creada.")
            return redirect("areas_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = AreaForm()
    return TemplateResponse(request, "catalog/area_form.html", {"form": form, "is_new": True})

@login_required
@user_passes_test(is_admin)
def area_edit(request, pk):
    obj = get_object_or_404(Area, pk=pk)
    if request.method == "POST":
        form = AreaForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Área actualizada.")
            return redirect("areas_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = AreaForm(instance=obj)
    return TemplateResponse(request, "catalog/area_form.html", {"form": form, "is_new": False, "obj": obj})

