"""Distância no mapa sem extensão geográfica (DP-17, BE-067).

Duas etapas, como decidido para o banco sem PostGIS:

1. **Caixa envolvente** (`bounding_box`): faixa de latitude/longitude que contém
   o círculo do raio. Vira `BETWEEN` nas colunas `latitude`/`longitude`, que têm
   índice B-tree, e descarta quase tudo cedo.
2. **Haversine** (`HaversineKm`): distância exata em km sobre a esfera (raio
   médio da Terra), calculada só para o que passou pela caixa; filtra `<= raio`
   e ordena por proximidade.
"""

import math
from dataclasses import dataclass

from django.db.models import F, FloatField, Func

EARTH_RADIUS_KM = 6371.0088
# 1° de arco na MESMA esfera do Haversine (≈ 111,195 km). Usar 111,32 (elipsoide no
# equador) deixaria a caixa menor que o círculo e cortaria pontos na borda do raio.
KM_PER_DEGREE_LAT = 2 * math.pi * EARTH_RADIUS_KM / 360
# Folga da caixa: ela só pré-filtra; quem decide é o Haversine.
BOX_MARGIN = 1.01

_HAVERSINE_SQL = (
    "(2 * {radius} * asin(LEAST(1.0, sqrt("
    "power(sin(radians((CAST({lat_col} AS double precision) - %s) / 2)), 2) "
    "+ cos(radians(%s)) * cos(radians(CAST({lat_col} AS double precision))) "
    "* power(sin(radians((CAST({lng_col} AS double precision) - %s) / 2)), 2)"
    "))))"
)


@dataclass(frozen=True)
class Box:
    min_lat: float
    max_lat: float
    min_lng: float | None
    max_lng: float | None


def bounding_box(lat: float, lng: float, radius_km: float) -> Box:
    """Caixa que contém o círculo. Perto dos polos ou cruzando o antimeridiano a
    faixa de longitude não se aplica (`None`): fica só a de latitude."""
    delta_lat = BOX_MARGIN * radius_km / KM_PER_DEGREE_LAT
    min_lat, max_lat = max(lat - delta_lat, -90.0), min(lat + delta_lat, 90.0)

    cos_lat = math.cos(math.radians(lat))
    if cos_lat < 1e-6 or min_lat <= -90.0 or max_lat >= 90.0:
        return Box(min_lat, max_lat, None, None)
    delta_lng = BOX_MARGIN * radius_km / (KM_PER_DEGREE_LAT * cos_lat)
    min_lng, max_lng = lng - delta_lng, lng + delta_lng
    if min_lng < -180.0 or max_lng > 180.0:
        return Box(min_lat, max_lat, None, None)
    return Box(min_lat, max_lat, min_lng, max_lng)


def box_filter(box: Box, lat_field: str, lng_field: str) -> dict:
    """Kwargs de `filter()` da caixa (usa o índice B-tree das coordenadas)."""
    lookups = {f"{lat_field}__range": (box.min_lat, box.max_lat)}
    if box.min_lng is not None:
        lookups[f"{lng_field}__range"] = (box.min_lng, box.max_lng)
    return lookups


class HaversineKm(Func):
    """Distância em km entre as colunas (lat_field, lng_field) e o ponto (lat, lng).

    `LEAST(1, …)` protege o `asin` de arredondamentos acima de 1. As colunas são
    DECIMAL(9,6) e são convertidas para double precision; o ponto de referência
    vai como parâmetro (float já validado), nunca como texto no SQL.
    """

    output_field = FloatField()

    def __init__(self, lat_field: str, lng_field: str, lat: float, lng: float):
        self._lat = float(lat)
        self._lng = float(lng)
        super().__init__(F(lat_field), F(lng_field))

    def as_sql(self, compiler, connection, **extra_context):
        lat_sql, lat_params = compiler.compile(self.source_expressions[0])
        lng_sql, lng_params = compiler.compile(self.source_expressions[1])
        sql = _HAVERSINE_SQL.format(
            radius=repr(EARTH_RADIUS_KM), lat_col=lat_sql, lng_col=lng_sql
        )
        # Ordem no SQL: lat_col, %s(lat), %s(lat), lat_col, lng_col, %s(lng).
        params = [
            *lat_params,
            self._lat,
            self._lat,
            *lat_params,
            *lng_params,
            self._lng,
        ]
        return sql, params


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """A mesma fórmula em Python (testes e conferência)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
