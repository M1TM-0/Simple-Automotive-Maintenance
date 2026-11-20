"""Oficina logada: conta, página, horários e ponto no mapa (BE-037…BE-040)."""

from decimal import Decimal

from apps.core import limits
from apps.core.fields import ImageURLField, media_url
from apps.core.serializers import OptionalTextField
from apps.workshops.models import EstablishmentType
from rest_framework import serializers

COORDINATE_PLACES = Decimal("0.000001")


class PointSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    name = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    address = serializers.CharField(read_only=True, allow_null=True)
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)


class PageSerializer(serializers.Serializer):
    description = serializers.CharField(read_only=True, allow_null=True)
    photo_profile = ImageURLField(read_only=True)
    photo_banner = ImageURLField(read_only=True)


class WorkshopMeSerializer(serializers.Serializer):
    """`GET /workshop/me/` (formato de PENDENCIAS-API.md §3)."""

    id = serializers.IntegerField(source="pk", read_only=True)
    name_fantasy = serializers.CharField(read_only=True)
    name_responsible = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True)
    phone_number = serializers.CharField(read_only=True, allow_null=True)
    cnpj = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    setup_complete = serializers.SerializerMethodField()
    point = serializers.SerializerMethodField()
    page = serializers.SerializerMethodField()

    def get_setup_complete(self, obj) -> bool:
        from apps.workshops.domain import is_setup_complete

        return is_setup_complete(obj)

    @staticmethod
    def _page(obj):
        from apps.workshops.models import PagWorkshop

        try:
            return obj.page
        except PagWorkshop.DoesNotExist:
            return None

    def get_point(self, obj) -> dict | None:
        point = obj.point_of_interest
        return PointSerializer(point).data if point else None

    def get_page(self, obj) -> dict:
        page = self._page(obj)
        if page is None:
            return {"description": None, "photo_profile": None, "photo_banner": None}
        return PageSerializer(page, context=self.context).data


class WorkshopMeUpdateSerializer(serializers.Serializer):
    """`PATCH /workshop/me/`: `cnpj`, `email` e `status` não estão aqui (ignorados)."""

    name_fantasy = serializers.CharField(required=False, max_length=255)
    name_responsible = serializers.CharField(required=False, max_length=255)
    phone_number = OptionalTextField(max_length=255)


class PageUpdateSerializer(serializers.Serializer):
    """`PATCH /workshop/page/` (multipart). Imagem vazia (`""`) remove."""

    description = OptionalTextField(max_length=limits.DESCRIPTION)
    photo_profile = ImageURLField(required=False)
    photo_banner = ImageURLField(required=False)


class OperationHourSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    day_of_week = serializers.IntegerField(read_only=True)
    opening_time = serializers.TimeField(read_only=True, format="%H:%M")
    closing_time = serializers.TimeField(read_only=True, format="%H:%M")


class OperationHourInputSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=1, max_value=7)
    opening_time = serializers.TimeField()
    closing_time = serializers.TimeField()

    def validate(self, attrs):
        if attrs["closing_time"] <= attrs["opening_time"]:
            raise serializers.ValidationError(
                {
                    "closing_time": [
                        "O horário de fechamento deve ser posterior ao de abertura."
                    ]
                }
            )
        return attrs


class PointOfInterestSearchSerializer(PointSerializer):
    claimed = serializers.SerializerMethodField(
        help_text="Já vinculado a OUTRA oficina (não pode ser escolhido)."
    )
    mine = serializers.SerializerMethodField(help_text="É o ponto atual desta oficina.")

    def get_claimed(self, obj) -> bool:
        owner = obj.owner_id
        return owner is not None and owner != self.context["workshop_id"]

    def get_mine(self, obj) -> bool:
        return obj.owner_id == self.context["workshop_id"]


class CoordinateField(serializers.DecimalField):
    """Coordenada em graus: aceita número ou texto e arredonda a 6 casas (DECIMAL(9,6))."""

    def __init__(self, limit, **kwargs):
        self.limit = Decimal(limit)
        super().__init__(max_digits=None, decimal_places=None, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data).quantize(COORDINATE_PLACES)
        if not -self.limit <= value <= self.limit:
            raise serializers.ValidationError(
                f"Informe um valor entre -{self.limit} e {self.limit}."
            )
        return value


class PointLinkSerializer(serializers.Serializer):
    """`POST /workshop/point/`: `{id_point_of_interest}` ou `{name,type,latitude,longitude,address}`."""

    id_point_of_interest = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    type = serializers.ChoiceField(choices=EstablishmentType.choices, required=False)
    latitude = CoordinateField(90, required=False)
    longitude = CoordinateField(180, required=False)
    address = OptionalTextField(max_length=limits.ADDRESS)

    def validate(self, attrs):
        if attrs.get("id_point_of_interest") is not None:
            return {"id_point_of_interest": attrs["id_point_of_interest"]}

        errors = {}
        name = (attrs.get("name") or "").strip()
        if not name:
            errors["name"] = ["Informe o nome do ponto."]
        for field in ("latitude", "longitude"):
            if attrs.get(field) is None:
                errors[field] = ["Este campo é obrigatório."]
        if errors:
            raise serializers.ValidationError(errors)
        attrs["name"] = name
        attrs.setdefault("type", EstablishmentType.WORKSHOP)
        attrs.pop("id_point_of_interest", None)
        return attrs


# ------------------------------------------------------- público (BE-065, BE-067)


class PublicServiceSerializer(serializers.Serializer):
    """Serviço no perfil público: sem dados internos da solicitação (motivo de recusa…)."""

    id = serializers.IntegerField(source="pk", read_only=True)
    id_service = serializers.IntegerField(
        source="service_id", read_only=True, allow_null=True
    )
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    id_service_category = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    price_base = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    duration_estimate = serializers.IntegerField(read_only=True)
    disponibility = serializers.BooleanField(read_only=True)

    def get_name(self, obj) -> str:
        return obj.name_local or obj.service.name

    def get_description(self, obj) -> str | None:
        if obj.description_local:
            return obj.description_local
        return obj.service.description if obj.service_id else None

    def get_id_service_category(self, obj) -> int | None:
        return obj.service.category_id if obj.service_id else obj.suggested_category_id

    def get_category_name(self, obj) -> str | None:
        if obj.service_id:
            return obj.service.category.name
        return obj.suggested_category.name if obj.suggested_category_id else None


class PublicWorkshopSerializer(serializers.Serializer):
    """`GET /workshops/{id}/` — campos planos (o `normWorkshop` do frontend aceita).

    Nunca inclui `cnpj`, `email`, `name_responsible`, `status` nem `password_hash`.
    """

    id = serializers.IntegerField(source="pk", read_only=True)
    name_fantasy = serializers.CharField(read_only=True)
    phone_number = serializers.CharField(read_only=True, allow_null=True)
    description = serializers.SerializerMethodField()
    photo_profile = serializers.SerializerMethodField()
    photo_banner = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField(
        help_text="Tipo do ponto no mapa; `oficina` se não houver ponto."
    )
    operation_hours = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField(
        help_text="Média das avaliações publicadas (1 casa)."
    )
    rating_count = serializers.IntegerField(read_only=True)
    is_favorite = serializers.SerializerMethodField(
        help_text="Só com sessão de cliente; senão `null`."
    )
    is_open_now = serializers.SerializerMethodField(
        help_text="Pelos horários e o fuso do negócio (DP-16); `null` se não houver horários."
    )

    @staticmethod
    def _page(obj):
        from apps.workshops.models import PagWorkshop

        try:
            return obj.page
        except PagWorkshop.DoesNotExist:
            return None

    def _page_image(self, obj, field):
        page = self._page(obj)
        if page is None:
            return None
        return media_url(getattr(page, field), self.context.get("request"))

    def get_description(self, obj) -> str | None:
        page = self._page(obj)
        return page.description if page else None

    def get_photo_profile(self, obj) -> str | None:
        return self._page_image(obj, "photo_profile")

    def get_photo_banner(self, obj) -> str | None:
        return self._page_image(obj, "photo_banner")

    def get_address(self, obj) -> str | None:
        point = obj.point_of_interest
        return point.address if point else None

    def get_latitude(self, obj) -> float | None:
        point = obj.point_of_interest
        return float(point.latitude) if point else None

    def get_longitude(self, obj) -> float | None:
        point = obj.point_of_interest
        return float(point.longitude) if point else None

    def get_type(self, obj) -> str:
        point = obj.point_of_interest
        return point.type if point else EstablishmentType.WORKSHOP.value

    def get_operation_hours(self, obj) -> list[dict]:
        return OperationHourSerializer(obj.public_hours, many=True).data

    def get_services(self, obj) -> list[dict]:
        return PublicServiceSerializer(obj.public_services, many=True).data

    def get_rating_avg(self, obj) -> float | None:
        from apps.reviews.selectors import round_rating

        return round_rating(obj.rating_avg)

    def get_is_favorite(self, obj) -> bool | None:
        return getattr(obj, "is_favorite", None)

    def get_is_open_now(self, obj) -> bool | None:
        from apps.workshops.domain import is_open_at

        return is_open_at(obj.public_hours)


class MapPointSerializer(serializers.Serializer):
    """Item de `GET /map/points/` (linha do UNION, colunas `m_*`).

    POI omite `rating_avg`, `rating_count` e `is_open_now`; `distance_km` só vem
    quando a busca informa `lat`/`lng`. Oficina sem horários: `is_open_now` omitido.
    """

    kind = serializers.ChoiceField(
        choices=[("workshop", "Oficina"), ("poi", "Ponto de interesse")]
    )
    id = serializers.IntegerField()
    name = serializers.CharField()
    type = serializers.CharField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    address = serializers.CharField(allow_null=True)
    distance_km = serializers.FloatField(
        required=False, help_text="km, 2 casas; só com lat/lng."
    )
    rating_avg = serializers.FloatField(
        required=False, allow_null=True, help_text="Só oficinas."
    )
    rating_count = serializers.IntegerField(required=False, help_text="Só oficinas.")
    is_open_now = serializers.BooleanField(
        required=False, help_text="Só oficinas com horários."
    )

    def to_representation(self, row):
        item = {
            "kind": row["m_kind"],
            "id": row["m_id"],
            "name": row["m_name"],
            "type": row["m_type"],
            "lat": row["m_lat"],
            "lng": row["m_lng"],
            "address": row["m_address"],
        }
        if row["m_distance"] is not None:
            item["distance_km"] = round(row["m_distance"], 2)
        if row["m_kind"] == "workshop":
            rating = row["m_rating_avg"]
            item["rating_avg"] = None if rating is None else round(rating, 1)
            item["rating_count"] = row["m_rating_count"]
            if row["m_has_hours"]:
                item["is_open_now"] = bool(row["m_open"])
        return item


MAX_RADIUS_KM = 100
DEFAULT_RADIUS_KM = 10


class MapQuerySerializer(serializers.Serializer):
    """Filtros de `GET /map/points/` (valores inválidos → 400 no campo)."""

    q = serializers.CharField(
        required=False, allow_blank=True, max_length=limits.SEARCH
    )
    category = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Id ou nome da categoria de serviço (só oficinas).",
    )
    type = serializers.ChoiceField(
        choices=EstablishmentType.choices, required=False, allow_blank=True
    )
    open_now = serializers.BooleanField(required=False, default=False)
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, min_value=-180, max_value=180)
    radius_km = serializers.FloatField(
        required=False,
        min_value=0.1,
        max_value=MAX_RADIUS_KM,
        help_text=f"Raio em km (padrão {DEFAULT_RADIUS_KM}, máximo {MAX_RADIUS_KM}); exige lat/lng.",
    )

    def validate(self, attrs):
        has_lat, has_lng = attrs.get("lat") is not None, attrs.get("lng") is not None
        if has_lat != has_lng:
            missing = "lng" if has_lat else "lat"
            raise serializers.ValidationError(
                {missing: ["Informe latitude e longitude juntas."]}
            )
        if attrs.get("radius_km") is not None and not has_lat:
            raise serializers.ValidationError(
                {"radius_km": ["O raio exige lat e lng."]}
            )
        if has_lat:
            attrs.setdefault("radius_km", DEFAULT_RADIUS_KM)
        return attrs


# ------------------------------------------------- estabelecimentos externos (BE-094)

EXTERNAL_TYPES = [
    ("posto_combustivel", "Posto de combustível"),
    ("borracharia", "Borracharia"),
    ("oficina", "Oficina"),
    ("loja_autopecas", "Loja de autopeças"),
    ("lava_jato", "Lava-jato"),
    ("outro", "Outro"),
]


class ExternalPointsQuerySerializer(serializers.Serializer):
    """Caixa visível do mapa (`GET /map/external-points/`); inválida → 400 no campo."""

    south = serializers.FloatField(min_value=-90, max_value=90)
    west = serializers.FloatField(min_value=-180, max_value=180)
    north = serializers.FloatField(min_value=-90, max_value=90)
    east = serializers.FloatField(min_value=-180, max_value=180)

    def validate(self, attrs):
        if attrs["north"] <= attrs["south"]:
            raise serializers.ValidationError(
                {"north": ["`north` deve ser maior que `south`."]}
            )
        if attrs["east"] <= attrs["west"]:
            raise serializers.ValidationError(
                {"east": ["`east` deve ser maior que `west`."]}
            )
        return attrs


class ExternalPointSerializer(serializers.Serializer):
    """Estabelecimento do OpenStreetMap **não cadastrado** no SAM (só exibição)."""

    id = serializers.CharField(help_text="`osm:<tipo>:<id>` — não é id do SAM.")
    osm_type = serializers.ChoiceField(choices=["node", "way", "relation"])
    osm_id = serializers.IntegerField()
    name = serializers.CharField()
    has_name = serializers.BooleanField(
        help_text="`false`: o OSM não tem nome; `name` é o tipo."
    )
    type = serializers.ChoiceField(choices=EXTERNAL_TYPES)
    osm_tag = serializers.CharField(
        help_text="Etiqueta do OSM que classificou o ponto (ex.: `amenity=fuel`)."
    )
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    address = serializers.CharField(allow_null=True)
    osm_url = serializers.URLField()


class ExternalPointsResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["ok", "partial", "unavailable", "too_large", "disabled"],
        help_text=(
            "`ok`: região completa; `partial`: parte veio do cache e o resto falhou; "
            "`unavailable`: Overpass fora do ar, lenta ou no limite; `too_large`: região "
            "grande demais (aproxime o mapa); `disabled`: desligado na configuração."
        ),
    )
    detail = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    attribution = serializers.CharField()
    license = serializers.CharField()
    license_url = serializers.URLField()
    count = serializers.IntegerField()
    results = ExternalPointSerializer(many=True)
