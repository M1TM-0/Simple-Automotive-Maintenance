"""Leituras públicas da oficina: perfil (BE-065) e pontos do mapa (BE-067).

**Oficina pública (DP-20):** conta `active` **e** cadastro concluído (≥ 1 serviço
não rejeitado, DP-06). Inativa, bloqueada ou ainda no assistente → 404 no perfil
e ausente do mapa, das promoções e das listas públicas.

Nada aqui seleciona `cnpj`, `email`, `name_responsible` nem `password_hash`.
"""

from apps.accounts.models import AccountStatus, Workshop
from apps.catalog.models import SolicitationStatus, WorkshopService
from apps.core.search import normalize_search_text, normalized, search_filter
from apps.reviews.selectors import rating_annotations
from apps.workshops.domain import business_clock
from apps.workshops.geo import HaversineKm, bounding_box, box_filter
from apps.workshops.models import OperationHour, PointOfInterest
from django.db.models import (
    BooleanField,
    CharField,
    Exists,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Value,
)
from django.db.models.functions import Cast


def _active_services(workshop_ref="pk"):
    """Serviços que contam para o cadastro (DP-06): tudo, menos solicitação rejeitada."""
    return WorkshopService.objects.filter(workshop_id=OuterRef(workshop_ref)).exclude(
        status_solicitation=SolicitationStatus.REJECTED
    )


def public_workshops():
    """Oficinas visíveis ao público (DP-20)."""
    return Workshop.objects.filter(status=AccountStatus.ACTIVE).filter(
        Exists(_active_services())
    )


def public_workshop_ids():
    return public_workshops().values("pk")


def public_workshop_or_404(workshop_id: int):
    """Oficina pública ou 404 (listas públicas `/workshops/{id}/…`)."""
    from rest_framework.exceptions import NotFound

    workshop = (
        public_workshops().filter(pk=workshop_id).only("pk", "name_fantasy").first()
    )
    if workshop is None:
        raise NotFound("Oficina não encontrada.")
    return workshop


def public_services():
    """Serviços exibidos no perfil: disponíveis e não rejeitados (personalizados
    `pending` entram — ficam disponíveis de imediato na oficina)."""
    return (
        WorkshopService.objects.filter(disponibility=True)
        .exclude(status_solicitation=SolicitationStatus.REJECTED)
        .select_related("service__category", "suggested_category")
        .order_by("id_workshop_service")
    )


def workshop_profile(workshop_id: int, client_id: int | None = None):
    """Uma oficina pública com página, ponto, horários, serviços e nota (consultas fixas)."""
    from apps.accounts.models import Favorite

    queryset = (
        public_workshops()
        .filter(pk=workshop_id)
        .select_related("page", "point_of_interest")
        .annotate(**rating_annotations())
        .prefetch_related(
            Prefetch(
                "operation_hours",
                queryset=OperationHour.objects.order_by("day_of_week", "opening_time"),
                to_attr="public_hours",
            ),
            Prefetch("services", queryset=public_services(), to_attr="public_services"),
        )
    )
    if client_id is not None:
        favorite = Favorite.objects.filter(
            workshop_id=OuterRef("pk"), client_id=client_id
        )
        queryset = queryset.annotate(is_favorite=Exists(favorite))
    return queryset.first()


# ---------------------------------------------------------------- mapa (BE-067)

# Colunas comuns às duas metades do UNION (oficinas e POIs). Os nomes têm prefixo
# `m_` porque `name`, `type`, `latitude`… já são campos de PointOfInterest.
MAP_COLUMNS = (
    "m_kind",
    "m_id",
    "m_name",
    "m_type",
    "m_lat",
    "m_lng",
    "m_address",
    "m_distance",
    "m_rating_avg",
    "m_rating_count",
    "m_open",
    "m_has_hours",
)


def _open_now_exists(day, now, workshop_ref="pk"):
    return Exists(
        OperationHour.objects.filter(
            workshop_id=OuterRef(workshop_ref),
            day_of_week=day,
            opening_time__lte=now,
            closing_time__gt=now,
        )
    )


def _category_exists(category_ids):
    """Oficina com serviço disponível numa das categorias (global ou sugerida)."""
    return Exists(
        WorkshopService.objects.filter(workshop_id=OuterRef("pk"), disponibility=True)
        .exclude(status_solicitation=SolicitationStatus.REJECTED)
        .filter(
            Q(service__category_id__in=category_ids)
            | Q(service__isnull=True, suggested_category_id__in=category_ids)
        )
    )


def _service_name_exists(term):
    services = search_filter(
        WorkshopService.objects.filter(
            workshop_id=OuterRef("pk"), disponibility=True
        ).exclude(status_solicitation=SolicitationStatus.REJECTED),
        term,
        "name_local",
        "service__name",
    )
    return Exists(services)


def _project(queryset, columns):
    """`annotate` + `values` na ordem de MAP_COLUMNS (as duas metades do UNION batem)."""
    return queryset.annotate(**{name: columns[name] for name in MAP_COLUMNS}).values(
        *MAP_COLUMNS
    )


def map_points(filters: dict):
    """UNION de oficinas públicas com ponto (`workshop`) e POIs não vinculados (`poi`).

    `filters` (já validado pela view): `q`, `category_ids` (lista ou None), `type`,
    `open_now` (bool), `lat`/`lng`/`radius_km` (todos ou nenhum).

    - POI vinculado a uma oficina nunca aparece como `poi` (sem duplicata); só
      aparece como `workshop`, e só se a oficina for pública. Oficina sem ponto
      não aparece (P4).
    - `category` e `open_now` só se aplicam a oficinas: com eles os POIs saem.
    """
    day, now = business_clock()
    near = filters.get("lat") is not None
    term = normalize_search_text(filters.get("q"))

    workshops = public_workshops().filter(point_of_interest__isnull=False)
    pois = PointOfInterest.objects.filter(workshop__isnull=True)

    if term:
        workshops = workshops.alias(_q_name=normalized("name_fantasy")).filter(
            Q(_q_name__contains=term) | Q(_service_name_exists(term))
        )
        pois = search_filter(pois, term, "name")
    if filters.get("type"):
        workshops = workshops.filter(point_of_interest__type=filters["type"])
        pois = pois.filter(type=filters["type"])
    if filters.get("category_ids") is not None:
        workshops = workshops.filter(_category_exists(filters["category_ids"]))
        pois = pois.none()
    if filters.get("open_now"):
        workshops = workshops.filter(_open_now_exists(day, now))
        pois = pois.none()

    null_float = Value(None, output_field=FloatField())
    if near:
        lat, lng, radius = filters["lat"], filters["lng"], filters["radius_km"]
        box = bounding_box(lat, lng, radius)
        workshops = workshops.filter(
            **box_filter(
                box, "point_of_interest__latitude", "point_of_interest__longitude"
            )
        ).alias(
            _dist=HaversineKm(
                "point_of_interest__latitude", "point_of_interest__longitude", lat, lng
            )
        )
        workshops = workshops.filter(_dist__lte=radius)
        pois = pois.filter(**box_filter(box, "latitude", "longitude")).alias(
            _dist=HaversineKm("latitude", "longitude", lat, lng)
        )
        pois = pois.filter(_dist__lte=radius)
        workshop_distance = HaversineKm(
            "point_of_interest__latitude", "point_of_interest__longitude", lat, lng
        )
        poi_distance = HaversineKm("latitude", "longitude", lat, lng)
    else:
        workshop_distance = poi_distance = null_float

    ratings = rating_annotations()
    workshop_columns = {
        "m_kind": Value("workshop", output_field=CharField()),
        "m_id": F("pk"),
        "m_name": F("name_fantasy"),
        "m_type": F("point_of_interest__type"),
        "m_lat": Cast("point_of_interest__latitude", FloatField()),
        "m_lng": Cast("point_of_interest__longitude", FloatField()),
        "m_address": F("point_of_interest__address"),
        "m_distance": workshop_distance,
        "m_rating_avg": Cast(ratings["rating_avg"], FloatField()),
        "m_rating_count": ratings["rating_count"],
        "m_open": _open_now_exists(day, now),
        "m_has_hours": Exists(OperationHour.objects.filter(workshop_id=OuterRef("pk"))),
    }
    poi_columns = {
        "m_kind": Value("poi", output_field=CharField()),
        "m_id": F("pk"),
        "m_name": F("name"),
        "m_type": F("type"),
        "m_lat": Cast("latitude", FloatField()),
        "m_lng": Cast("longitude", FloatField()),
        "m_address": F("address"),
        "m_distance": poi_distance,
        "m_rating_avg": null_float,
        "m_rating_count": Value(None, output_field=IntegerField()),
        "m_open": Value(None, output_field=BooleanField()),
        "m_has_hours": Value(False, output_field=BooleanField()),
    }

    combined = _project(workshops, workshop_columns).union(
        _project(pois, poi_columns), all=True
    )
    if near:
        return combined.order_by("m_distance", "m_kind", "m_id")
    # Sem posição: oficinas cadastradas primeiro (o "kind" 'poi' > 'workshop' em ordem
    # alfabética, daí o DESC), depois por nome.
    return combined.order_by("-m_kind", "m_name", "m_id")


def category_ids_for(value: str) -> list[int]:
    """`category` do mapa: id numérico ou nome da categoria (sem acentos/caixa)."""
    from apps.catalog.models import ServiceCategory

    if value.isdigit():
        return [int(value)]
    term = normalize_search_text(value)
    return list(
        ServiceCategory.objects.alias(_n=normalized("name"))
        .filter(_n=term)
        .values_list("pk", flat=True)
    )


# ------------------------------------------------- estabelecimentos externos (BE-094)

# ≈ 160 m: cobre o raio de duplicata (100 m) com folga em qualquer latitude do Brasil.
_DEDUP_MARGIN_DEGREES = 0.0015
_DEDUP_LIMIT = 5000


def sam_points_for_dedup(south, west, north, east):
    """Pontos do SAM (vinculados ou não a oficina) em volta da caixa, para tirar dos
    estabelecimentos do OpenStreetMap o que já está no SAM (`overpass.drop_sam_duplicates`).

    Considera todo ponto, inclusive de oficina não pública: o que o SAM conhece não é
    repetido como "externo". Só lê nome, posição e identificação na fonte.
    """
    m = _DEDUP_MARGIN_DEGREES
    rows = PointOfInterest.objects.filter(
        latitude__range=(south - m, north + m),
        longitude__range=(west - m, east + m),
    ).values(
        "latitude",
        "longitude",
        "name",
        "external_source",
        "external_id",
        "workshop__name_fantasy",
    )[:_DEDUP_LIMIT]
    return [
        {
            "lat": float(row["latitude"]),
            "lng": float(row["longitude"]),
            "names": (row["name"], row["workshop__name_fantasy"]),
            "external_source": row["external_source"],
            "external_id": row["external_id"],
        }
        for row in rows
    ]
