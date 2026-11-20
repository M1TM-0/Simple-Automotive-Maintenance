from django.conf import settings
from django.db import models
from django.templatetags.static import static
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .images import InvalidImageError, process_image


class StoredImageField(models.CharField):
    """Coluna VARCHAR que guarda o caminho de uma imagem no storage."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 500)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


def media_url(name, request=None):
    if not name:
        return None

    if name == settings.SAM_DEFAULT_PROFILE_IMAGE:
        url = static("core/default-profile.png")
    elif name.startswith(("http://", "https://")):
        return name
    elif name.startswith("/"):
        url = name
    else:
        url = f"{settings.MEDIA_URL.rstrip('/')}/{name}"

    return request.build_absolute_uri(url) if request is not None else url


@extend_schema_field(OpenApiTypes.URI)
class ImageURLField(serializers.Field):
    """Leitura: URL da imagem. Escrita: arquivo validado, ou vazio para remover."""

    default_error_messages = {"invalid": "Envie um arquivo de imagem."}

    def __init__(self, **kwargs):
        kwargs.pop("max_length", None)
        kwargs.pop("allow_blank", None)
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)
        self.allow_blank = True

    def to_representation(self, value):
        return media_url(value, self.context.get("request"))

    def to_internal_value(self, data):
        if data in ("", None):
            return None
        if not hasattr(data, "read"):
            self.fail("invalid")
        try:
            return process_image(data)
        except InvalidImageError as exc:
            raise serializers.ValidationError(str(exc)) from None
