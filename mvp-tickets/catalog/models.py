from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.name

class Priority(models.Model):
    name = models.CharField(max_length=120, unique=True)
    sla_hours = models.PositiveIntegerField(default=72)

    def __str__(self):
        return self.name

class Area(models.Model):
    name = models.CharField(max_length=120, unique=True)
    def __str__(self): return self.name

