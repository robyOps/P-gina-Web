from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower

class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().upper()
        super().save(*args, **kwargs)


class Subcategory(models.Model):
    """Vocabulary controlled at category level."""

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
        return f"{self.category.name} · {self.name}" if self.category_id else self.name

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

class Priority(models.Model):
    name = models.CharField(max_length=120, unique=True)
    sla_hours = models.PositiveIntegerField(default=72)

    def __str__(self):
        return self.name

class Area(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name

