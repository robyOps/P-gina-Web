"""
===============================================================================
Propósito:
    Definir entidades de catálogo usadas por los tickets (categorías, prioridades,
    áreas y subcategorías).
API pública:
    Modelos Django ``Category``, ``Subcategory``, ``Priority`` y ``Area``.
Flujo de datos:
    Datos administrados → validaciones ORM → normalización en ``save`` → uso en
    relaciones de ``tickets``.
Dependencias:
    Django ORM y funciones utilitarias para restricciones case-insensitive.
Decisiones:
    Se normaliza el nombre a mayúsculas para evitar duplicados y se añade una
    restricción única por categoría/subcategoría.
TODOs:
    TODO:PREGUNTA Confirmar si la normalización a mayúsculas afecta integraciones
    externas que requieran formato original.
===============================================================================
"""

from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower


class Category(models.Model):
    """Representa la categoría principal para clasificar tickets."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        """Retorna el nombre como representación legible."""

        return self.name

    def save(self, *args, **kwargs):
        """Normaliza el nombre en mayúsculas para mantener consistencia."""

        if self.name:
            self.name = self.name.strip().upper()
        super().save(*args, **kwargs)


class Subcategory(models.Model):
    """Subclasificación dependiente de una categoría."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="subcategories",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__name", "name"]
        constraints = [
            UniqueConstraint(
                Lower("name"),
                "category",
                name="uniq_subcategory_per_category",
            )
        ]

    def __str__(self) -> str:
        """Retorna "Categoría · Subcategoría" para facilitar lectura."""

        return f"{self.category.name} · {self.name}" if self.category_id else self.name

    def save(self, *args, **kwargs):
        """Normaliza el nombre previo a guardar para evitar duplicados."""

        if self.name:
            self.name = self.name.strip().upper()
        super().save(*args, **kwargs)


class Priority(models.Model):
    """Representa una prioridad con su tiempo objetivo de atención."""

    name = models.CharField(max_length=120, unique=True)
    sla_hours = models.PositiveIntegerField(default=72)

    def __str__(self):
        """Retorna el nombre de la prioridad."""

        return self.name


class Area(models.Model):
    """Unidad organizacional responsable del ticket."""

    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        """Retorna el nombre del área."""

        return self.name
