from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.name

class Priority(models.Model):
    LOW="LOW"; MEDIUM="MEDIUM"; HIGH="HIGH"; CRITICAL="CRITICAL"
    KEY_CHOICES = [(LOW,"Baja"),(MEDIUM,"Media"),(HIGH,"Alta"),(CRITICAL,"Crítica")]
    key = models.CharField(max_length=10, choices=KEY_CHOICES, unique=True)
    sla_hours = models.PositiveIntegerField(default=72)
    def __str__(self): return dict(self.KEY_CHOICES).get(self.key, self.key)

class Area(models.Model):
    name = models.CharField(max_length=120, unique=True)
    def __str__(self): return self.name

