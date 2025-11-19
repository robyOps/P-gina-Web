# tickets/validators.py
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".doc", ".docx"}
ALLOWED_CT  = {
    "image/png", "image/jpeg", "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_SIZE = 20 * 1024 * 1024  # 20MB

class UploadValidationError(Exception):
    pass

def validate_upload(django_file):
    name = getattr(django_file, "name", "")
    size = getattr(django_file, "size", 0)
    ctyp = getattr(django_file, "content_type", "") or ""

    if Path(name).name != name:
        raise UploadValidationError("Nombre de archivo inválido.")

    if size > MAX_SIZE:
        raise UploadValidationError("Archivo demasiado grande (>20MB).")

    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise UploadValidationError(f"Extensión no permitida: {ext}")

    # content_type puede venir vacío; si viene, validamos
    if ctyp and ctyp not in ALLOWED_CT:
        raise UploadValidationError(f"Tipo de contenido no permitido: {ctyp}")


def _validate_size(django_file, *, max_bytes: int, label: str):
    size = getattr(django_file, "size", 0) or 0
    if size > max_bytes:
        raise ValidationError(f"{label} supera el límite permitido.")


def validate_faq_image(upload):
    if not upload:
        return
    max_bytes = getattr(settings, "FAQ_IMAGE_MAX_MB", 2) * 1024 * 1024
    _validate_size(upload, max_bytes=max_bytes, label="La imagen")
    ext = Path(getattr(upload, "name", "")).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise ValidationError("Formato de imagen no soportado.")


def validate_faq_video_file(upload):
    if not upload:
        return
    max_bytes = getattr(settings, "FAQ_VIDEO_MAX_MB", 25) * 1024 * 1024
    _validate_size(upload, max_bytes=max_bytes, label="El video")
    ext = Path(getattr(upload, "name", "")).suffix.lower()
    if ext != ".mp4":
        raise ValidationError("Solo se permiten videos MP4.")
