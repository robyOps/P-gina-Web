"""Modelos y señales asociados al manejo de usuarios."""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from catalog.models import Area


class UserProfile(models.Model):
    """Información adicional editable desde el mantenedor de usuarios."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    rut = models.CharField(
        max_length=12,
        blank=True,
        null=True,
        unique=True,
        help_text="RUT normalizado con guion (12345678-9).",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profiles",
    )

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self) -> str:  # pragma: no cover - representación simple
        return f"Perfil de {self.user.get_username()}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile_exists(sender, instance, created, **_: object) -> None:
    """Garantiza que cada usuario tenga un perfil asociado."""

    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)
