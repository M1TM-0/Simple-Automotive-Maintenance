from decimal import Decimal

from rest_framework.renderers import JSONRenderer
from rest_framework.utils.encoders import JSONEncoder


class SamJSONEncoder(JSONEncoder):
    """Valores monetários sempre como string decimal, sem notação científica."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return format(obj, "f")
        return super().default(obj)


class SamJSONRenderer(JSONRenderer):
    encoder_class = SamJSONEncoder
