import io
import uuid
from dataclasses import dataclass

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    extension: str
    content_type: str

    def random_name(self):
        return f"{uuid.uuid4().hex}.{self.extension}"


def process_image(upload):
    """Valida pelo conteúdo real e regrava a imagem sem metadados (EXIF, texto, ICC)."""
    max_bytes = settings.SAM_IMAGE_MAX_BYTES
    max_dimension = settings.SAM_IMAGE_MAX_DIMENSION

    size = getattr(upload, "size", None)
    if size is not None and size > max_bytes:
        raise InvalidImageError(
            f"A imagem excede o tamanho máximo de {max_bytes // (1024 * 1024)} MB."
        )

    raw = upload.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise InvalidImageError(
            f"A imagem excede o tamanho máximo de {max_bytes // (1024 * 1024)} MB."
        )
    if not raw:
        raise InvalidImageError("O arquivo enviado está vazio.")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            image_format = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise InvalidImageError("O arquivo enviado não é uma imagem válida.") from None

    if image_format == "MPO":
        # JPEG com vários quadros (fotos de celular com mapa de profundidade etc.):
        # mantém só o primeiro quadro e regrava como JPEG comum.
        image_format = "JPEG"

    if image_format not in ALLOWED_FORMATS:
        raise InvalidImageError(
            "Formato de imagem não suportado. Use JPEG, PNG ou WebP."
        )

    if width > max_dimension or height > max_dimension:
        raise InvalidImageError(
            f"A imagem excede {max_dimension}×{max_dimension} pixels."
        )

    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
    except (OSError, Image.DecompressionBombError):
        raise InvalidImageError("O arquivo enviado não é uma imagem válida.") from None

    extension, content_type = ALLOWED_FORMATS[image_format]
    output = io.BytesIO()

    if image_format == "JPEG":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(output, format="JPEG", quality=85, optimize=True)
    elif image_format == "PNG":
        image.save(output, format="PNG", optimize=True)
    else:
        image.save(output, format="WEBP", quality=85)

    return ProcessedImage(output.getvalue(), extension, content_type)
