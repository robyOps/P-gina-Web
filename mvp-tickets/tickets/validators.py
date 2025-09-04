# tickets/validators.py
from pathlib import Path

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
