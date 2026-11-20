"""BE-065 (perfil público da oficina) e BE-067 (pontos do mapa)."""

from datetime import datetime

import pytest
from apps.accounts.models import AccountStatus
from apps.catalog.models import ServiceCategory
from apps.core.tests.factories import (
    AttendanceFactory,
    FavoriteFactory,
    OperationHourFactory,
    PagWorkshopFactory,
    PointOfInterestFactory,
    ServiceFactory,
    WorkshopServiceFactory,
    deliver_attendance,
)
from apps.core.timeutils import business_timezone
from apps.reviews.models import Review
from apps.workshops.geo import bounding_box, haversine_km

MAP_URL = "/api/map/points/"
CENTER = (-5.089200, -42.801600)  # Teresina
KM_PER_DEGREE = 111.195  # 1° de latitude na esfera de raio 6371,0088 km


def profile_url(pk):
    return f"/api/workshops/{pk}/"


def north_of(km, base=CENTER):
    """Ponto `km` ao norte de `base` (mesma longitude)."""
    return round(base[0] + km / KM_PER_DEGREE, 6), base[1]


def make_public_workshop(name=None, coords=None, type="oficina", **workshop_kwargs):
    """Oficina pública (ativa + 1 serviço), com ponto no mapa se `coords`."""
    if name:
        workshop_kwargs["name_fantasy"] = name
    if coords is not None:
        workshop_kwargs["point_of_interest"] = PointOfInterestFactory(
            name=f"Ponto de {name or 'oficina'}",
            latitude=coords[0],
            longitude=coords[1],
            type=type,
        )
    page = PagWorkshopFactory(
        **{f"workshop__{k}": v for k, v in workshop_kwargs.items()}
    )
    WorkshopServiceFactory(workshop=page.workshop)
    return page.workshop


@pytest.fixture
def clock(monkeypatch):
    """Fixa o relógio do negócio (perfil e mapa leem `domain.business_now`)."""

    def set_clock(year, month, day, hour, minute=0):
        moment = datetime(year, month, day, hour, minute, tzinfo=business_timezone())
        monkeypatch.setattr("apps.workshops.domain.business_now", lambda: moment)
        return moment

    return set_clock


# ------------------------------------------------------------------ BE-065


@pytest.mark.django_db
class TestPublicProfile:
    def test_visitor_gets_full_profile_without_login(self, api_client):
        workshop = make_public_workshop(
            "Auto Center Silva", coords=CENTER, type="centro_automotivo"
        )
        OperationHourFactory(
            workshop=workshop, day_of_week=2, opening_time="13:00", closing_time="18:00"
        )
        OperationHourFactory(
            workshop=workshop, day_of_week=2, opening_time="08:00", closing_time="12:00"
        )

        response = api_client.get(profile_url(workshop.pk))

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == workshop.pk
        assert body["name_fantasy"] == "Auto Center Silva"
        assert body["description"] == "Página da oficina"
        assert body["photo_profile"].endswith("/static/core/default-profile.png")
        assert body["photo_banner"] is None
        assert body["type"] == "centro_automotivo"
        assert (body["latitude"], body["longitude"]) == CENTER
        assert [
            (h["day_of_week"], h["opening_time"]) for h in body["operation_hours"]
        ] == [
            (2, "08:00"),
            (2, "13:00"),
        ]
        assert len(body["services"]) == 1
        assert (body["rating_avg"], body["rating_count"]) == (None, 0)
        assert body["is_favorite"] is None

    def test_never_exposes_private_fields(self, api_client):
        workshop = make_public_workshop("Oficina Privada", coords=CENTER)

        response = api_client.get(profile_url(workshop.pk))

        body = response.json()
        for field in ("cnpj", "email", "password_hash", "name_responsible", "status"):
            assert field not in body
        text = response.content.decode()
        assert workshop.cnpj not in text
        assert workshop.email not in text
        assert workshop.password_hash not in text

    @pytest.mark.parametrize("status", [AccountStatus.BLOCKED, AccountStatus.INACTIVE])
    def test_blocked_or_inactive_workshop_is_404(self, api_client, status):
        workshop = make_public_workshop(status=status)

        response = api_client.get(profile_url(workshop.pk))

        assert response.status_code == 404
        assert response.json()["detail"] == "Oficina não encontrada."

    def test_workshop_without_finished_setup_is_404(self, api_client):
        workshop = (
            PagWorkshopFactory().workshop
        )  # sem serviço: cadastro não concluído (DP-20)

        assert api_client.get(profile_url(workshop.pk)).status_code == 404

    def test_unknown_workshop_is_404(self, api_client):
        assert api_client.get(profile_url(999_999)).status_code == 404

    def test_without_point_the_location_is_null(self, api_client):
        workshop = make_public_workshop()

        body = api_client.get(profile_url(workshop.pk)).json()

        assert (body["address"], body["latitude"], body["longitude"]) == (
            None,
            None,
            None,
        )
        assert body["type"] == "oficina"

    def test_services_are_available_ones_including_pending_custom(self, api_client):
        workshop = make_public_workshop()
        category = ServiceCategory.objects.get(name="Pneus")
        WorkshopServiceFactory(workshop=workshop, disponibility=False)
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Rodízio especial",
            suggested_category=category,
            status_solicitation="pending",
        )
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Recusado",
            suggested_category=category,
            status_solicitation="rejected",
            motivation_rejection="Duplicado",
            date_solicitation_response="2026-11-01T10:00:00Z",
        )

        services = api_client.get(profile_url(workshop.pk)).json()["services"]

        names = [s["name"] for s in services]
        assert len(services) == 2
        assert "Rodízio especial" in names and "Recusado" not in names
        custom = next(s for s in services if s["name"] == "Rodízio especial")
        assert custom["category_name"] == "Pneus"
        assert custom["price_base"] == "100.00"
        assert custom["duration_estimate"] == 60
        assert (
            "motivation_rejection" not in custom and "status_solicitation" not in custom
        )

    def test_rating_counts_only_published_reviews(self, api_client):
        workshop = make_public_workshop()
        for rating, status in (
            (4, "published"),
            (5, "published"),
            (1, "hidden"),
            (2, "under_review"),
        ):
            budget, *_ = deliver_attendance(AttendanceFactory(workshop=workshop))
            Review.objects.create(budget=budget, rating=rating, status_review=status)

        body = api_client.get(profile_url(workshop.pk)).json()

        assert (body["rating_avg"], body["rating_count"]) == (4.5, 2)

    def test_is_favorite_for_client_session(self, client_session, client_account):
        favorite = make_public_workshop()
        other = make_public_workshop()
        FavoriteFactory(client=client_account, workshop=favorite)

        assert (
            client_session.get(profile_url(favorite.pk)).json()["is_favorite"] is True
        )
        assert client_session.get(profile_url(other.pk)).json()["is_favorite"] is False

    def test_is_favorite_is_null_for_workshop_session(self, ready_workshop_session):
        workshop = make_public_workshop()

        assert (
            ready_workshop_session.get(profile_url(workshop.pk)).json()["is_favorite"]
            is None
        )

    def test_open_on_tuesday_10h_with_08_to_12(self, api_client, clock):
        moment = clock(2026, 11, 17, 10)
        assert moment.isoweekday() == 2
        workshop = make_public_workshop()
        OperationHourFactory(
            workshop=workshop, day_of_week=2, opening_time="08:00", closing_time="12:00"
        )

        assert api_client.get(profile_url(workshop.pk)).json()["is_open_now"] is True

    @pytest.mark.parametrize(
        ("day", "hour", "minute"),
        [
            (17, 12, 0),
            (17, 7, 59),
            (18, 10, 0),
        ],  # fecha às 12h (exclusivo); antes de abrir; quarta
    )
    def test_closed_outside_the_interval(self, api_client, clock, day, hour, minute):
        clock(2026, 11, day, hour, minute)
        workshop = make_public_workshop()
        OperationHourFactory(
            workshop=workshop, day_of_week=2, opening_time="08:00", closing_time="12:00"
        )

        assert api_client.get(profile_url(workshop.pk)).json()["is_open_now"] is False

    def test_open_now_is_null_without_hours(self, api_client):
        workshop = make_public_workshop()

        assert api_client.get(profile_url(workshop.pk)).json()["is_open_now"] is None

    def test_fixed_number_of_queries(self, api_client, django_assert_max_num_queries):
        workshop = make_public_workshop(coords=CENTER)
        for _ in range(5):
            WorkshopServiceFactory(workshop=workshop)
        for day in range(1, 8):
            OperationHourFactory(workshop=workshop, day_of_week=day)

        with django_assert_max_num_queries(4):
            assert api_client.get(profile_url(workshop.pk)).status_code == 200


# ------------------------------------------------------------------ BE-067


def results(response):
    assert response.status_code == 200, response.json()
    return response.json()["results"]


@pytest.mark.django_db
class TestMapPoints:
    def test_visitor_sees_workshops_and_pois(self, api_client):
        workshop = make_public_workshop("Auto Center Silva", coords=CENTER)
        poi = PointOfInterestFactory(name="Borracharia do Zé", type="borracharia")

        items = results(api_client.get(MAP_URL))

        kinds = {(i["kind"], i["id"]) for i in items}
        assert kinds == {("workshop", workshop.pk), ("poi", poi.pk)}
        assert items[0]["kind"] == "workshop"  # sem posição: oficinas primeiro

    def test_item_shapes(self, api_client):
        workshop = make_public_workshop("Oficina A", coords=CENTER)
        workshop.point_of_interest.address = "Rua 1, 100"
        workshop.point_of_interest.save(update_fields=["address"])
        PointOfInterestFactory(
            name="Posto B", type="posto_combustivel", latitude="-5.1", longitude="-42.8"
        )

        items = {i["kind"]: i for i in results(api_client.get(MAP_URL))}

        assert items["workshop"] == {
            "kind": "workshop",
            "id": workshop.pk,
            "name": "Oficina A",
            "type": "oficina",
            "lat": CENTER[0],
            "lng": CENTER[1],
            "address": "Rua 1, 100",
            "rating_avg": None,
            "rating_count": 0,
        }
        poi = items["poi"]
        assert set(poi) == {"kind", "id", "name", "type", "lat", "lng", "address"}
        assert (poi["lat"], poi["lng"], poi["type"]) == (
            -5.1,
            -42.8,
            "posto_combustivel",
        )

    def test_claimed_poi_appears_once_as_workshop(self, api_client):
        workshop = make_public_workshop("Oficina Dona", coords=CENTER)

        items = results(api_client.get(MAP_URL))

        assert [(i["kind"], i["id"]) for i in items] == [("workshop", workshop.pk)]

    def test_non_public_workshops_and_their_points_are_hidden(self, api_client):
        make_public_workshop("Bloqueada", coords=CENTER, status=AccountStatus.BLOCKED)
        point = PointOfInterestFactory()
        PagWorkshopFactory(
            workshop__point_of_interest=point
        )  # sem serviço (assistente)

        assert results(api_client.get(MAP_URL)) == []

    def test_workshop_without_point_is_not_on_the_map(self, api_client):
        make_public_workshop("Sem ponto")

        assert results(api_client.get(MAP_URL)) == []

    def test_radius_filters_and_orders_by_distance(self, api_client):
        far = make_public_workshop("Longe", coords=north_of(8))
        near = make_public_workshop("Perto", coords=north_of(1))
        middle_poi = PointOfInterestFactory(
            name="Meio", latitude=north_of(3)[0], longitude=CENTER[1]
        )
        edge = PointOfInterestFactory(
            name="Borda", latitude=north_of(4.9)[0], longitude=CENTER[1]
        )
        PointOfInterestFactory(
            name="Fora", latitude=north_of(5.2)[0], longitude=CENTER[1]
        )

        items = results(
            api_client.get(
                MAP_URL, {"lat": CENTER[0], "lng": CENTER[1], "radius_km": 5}
            )
        )

        assert [(i["kind"], i["id"]) for i in items] == [
            ("workshop", near.pk),
            ("poi", middle_poi.pk),
            ("poi", edge.pk),
        ]
        assert far.pk not in [i["id"] for i in items if i["kind"] == "workshop"]
        for item in items:
            expected = haversine_km(CENTER[0], CENTER[1], item["lat"], item["lng"])
            assert item["distance_km"] <= 5
            assert item["distance_km"] == pytest.approx(expected, abs=0.006)
        distances = [i["distance_km"] for i in items]
        assert distances == sorted(distances)

    def test_distance_with_known_coordinates(self, api_client):
        # Teresina → Timon (MA): ~4,4 km em linha reta pelas coordenadas abaixo.
        timon = (-5.094100, -42.836700)
        PointOfInterestFactory(name="Timon", latitude=timon[0], longitude=timon[1])

        item = results(
            api_client.get(
                MAP_URL, {"lat": CENTER[0], "lng": CENTER[1], "radius_km": 10}
            )
        )[0]

        assert item["distance_km"] == pytest.approx(
            haversine_km(*CENTER, *timon), abs=0.006
        )
        assert 3.8 < item["distance_km"] < 4.0

    def test_east_west_points_use_longitude_box(self, api_client):
        # 3 km a leste (longitude) entra; 30 km a leste fica fora.
        delta = 3 / (111.195 * 0.99605)  # cos(-5,09°) ≈ 0,99605
        inside = PointOfInterestFactory(
            latitude=CENTER[0], longitude=round(CENTER[1] + delta, 6)
        )
        PointOfInterestFactory(
            latitude=CENTER[0], longitude=round(CENTER[1] + 10 * delta, 6)
        )

        items = results(
            api_client.get(
                MAP_URL, {"lat": CENTER[0], "lng": CENTER[1], "radius_km": 5}
            )
        )

        assert [i["id"] for i in items] == [inside.pk]
        assert items[0]["distance_km"] == pytest.approx(3, abs=0.01)

    def test_default_radius_is_10_km(self, api_client):
        inside = PointOfInterestFactory(latitude=north_of(9)[0], longitude=CENTER[1])
        PointOfInterestFactory(latitude=north_of(11)[0], longitude=CENTER[1])

        items = results(api_client.get(MAP_URL, {"lat": CENTER[0], "lng": CENTER[1]}))

        assert [i["id"] for i in items] == [inside.pk]

    def test_without_position_there_is_no_distance(self, api_client):
        make_public_workshop(coords=CENTER)

        assert "distance_km" not in results(api_client.get(MAP_URL))[0]

    def test_category_by_name_returns_only_workshops_with_that_category(
        self, api_client
    ):
        tires = ServiceCategory.objects.get(name="Pneus")
        with_tires = make_public_workshop("Pneus & Cia", coords=CENTER)
        WorkshopServiceFactory(
            workshop=with_tires, service=ServiceFactory(category=tires)
        )
        make_public_workshop("Só motor", coords=north_of(1))
        PointOfInterestFactory(name="Borracharia (POI)", type="borracharia")

        for value in ("Pneus", "pneus", str(tires.pk)):
            items = results(api_client.get(MAP_URL, {"category": value}))
            assert [(i["kind"], i["id"]) for i in items] == [
                ("workshop", with_tires.pk)
            ], value

    def test_category_matches_custom_service_suggested_category(self, api_client):
        tires = ServiceCategory.objects.get(name="Pneus")
        workshop = make_public_workshop(coords=CENTER)
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Rodízio",
            suggested_category=tires,
            status_solicitation="pending",
        )

        items = results(api_client.get(MAP_URL, {"category": tires.pk}))

        assert [i["id"] for i in items] == [workshop.pk]

    def test_unknown_category_returns_nothing(self, api_client):
        make_public_workshop(coords=CENTER)

        assert results(api_client.get(MAP_URL, {"category": "Inexistente"})) == []

    def test_q_searches_names_and_workshop_services_without_accents(self, api_client):
        oil = ServiceFactory(name="Troca de óleo especial")
        by_service = make_public_workshop("Mecânica Central", coords=CENTER)
        WorkshopServiceFactory(workshop=by_service, service=oil)
        by_name = make_public_workshop("Óleo Express", coords=north_of(1))
        make_public_workshop("Outra", coords=north_of(2))
        poi = PointOfInterestFactory(name="Posto do Óleo")
        PointOfInterestFactory(name="Borracharia")

        items = results(api_client.get(MAP_URL, {"q": "OLEO"}))

        assert {(i["kind"], i["id"]) for i in items} == {
            ("workshop", by_service.pk),
            ("workshop", by_name.pk),
            ("poi", poi.pk),
        }

    def test_type_filter_applies_to_both_kinds(self, api_client):
        workshop = make_public_workshop(coords=CENTER, type="borracharia")
        make_public_workshop(coords=north_of(1), type="oficina")
        poi = PointOfInterestFactory(type="borracharia")
        PointOfInterestFactory(type="lava_jato")

        items = results(api_client.get(MAP_URL, {"type": "borracharia"}))

        assert {(i["kind"], i["id"]) for i in items} == {
            ("workshop", workshop.pk),
            ("poi", poi.pk),
        }

    def test_open_now_returns_only_open_workshops(self, api_client, clock):
        clock(2026, 11, 17, 10)  # terça, 10h
        open_one = make_public_workshop("Aberta", coords=CENTER)
        OperationHourFactory(
            workshop=open_one, day_of_week=2, opening_time="08:00", closing_time="12:00"
        )
        closed = make_public_workshop("Fechada", coords=north_of(1))
        OperationHourFactory(
            workshop=closed, day_of_week=2, opening_time="13:00", closing_time="18:00"
        )
        make_public_workshop("Sem horário", coords=north_of(2))
        PointOfInterestFactory()

        everything = {i["name"]: i for i in results(api_client.get(MAP_URL))}
        only_open = results(api_client.get(MAP_URL, {"open_now": "true"}))

        assert [i["id"] for i in only_open] == [open_one.pk]
        assert everything["Aberta"]["is_open_now"] is True
        assert everything["Fechada"]["is_open_now"] is False
        assert "is_open_now" not in everything["Sem horário"]
        assert all(
            "is_open_now" not in i for i in everything.values() if i["kind"] == "poi"
        )

    def test_rating_of_workshops(self, api_client):
        workshop = make_public_workshop(coords=CENTER)
        for rating in (3, 4):
            budget, *_ = deliver_attendance(AttendanceFactory(workshop=workshop))
            Review.objects.create(budget=budget, rating=rating)

        item = results(api_client.get(MAP_URL))[0]

        assert (item["rating_avg"], item["rating_count"]) == (3.5, 2)

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"lat": CENTER[0], "lng": CENTER[1], "radius_km": 1000}, "radius_km"),
            ({"lat": CENTER[0], "lng": CENTER[1], "radius_km": 0}, "radius_km"),
            ({"lat": CENTER[0]}, "lng"),
            ({"lng": CENTER[1]}, "lat"),
            ({"radius_km": 5}, "radius_km"),
            ({"lat": 120, "lng": 0}, "lat"),
            ({"lat": "abc", "lng": 0}, "lat"),
            ({"type": "padaria"}, "type"),
            ({"open_now": "talvez"}, "open_now"),
        ],
    )
    def test_invalid_filters_are_400(self, api_client, params, field):
        response = api_client.get(MAP_URL, params)

        assert response.status_code == 400
        assert field in response.json()

    def test_paginated_shape(self, api_client):
        for _ in range(3):
            PointOfInterestFactory()

        body = api_client.get(MAP_URL, {"page_size": 2}).json()

        assert body["count"] == 3
        assert len(body["results"]) == 2
        assert body["next"] == "/api/map/points/?page=2&page_size=2"

    def test_session_cookie_is_not_needed_nor_checked(self, client_session):
        PointOfInterestFactory()

        assert len(results(client_session.get(MAP_URL))) == 1


class TestGeo:
    def test_bounding_box_contains_circle(self):
        box = bounding_box(CENTER[0], CENTER[1], 5)

        assert box.min_lat < north_of(-5)[0] < north_of(5)[0] < box.max_lat
        assert box.min_lng < CENTER[1] < box.max_lng

    def test_bounding_box_near_pole_or_antimeridian_drops_longitude(self):
        assert bounding_box(89.99, 0, 50).min_lng is None
        assert bounding_box(0, 179.99, 50).min_lng is None

    def test_haversine_known_distance(self):
        # 1° de latitude ≈ 111,19 km na esfera de raio médio.
        assert haversine_km(0, 0, 1, 0) == pytest.approx(111.195, abs=0.01)


@pytest.mark.django_db
def test_point_right_at_the_edge_of_the_radius_is_included(api_client):
    # 4,999 km ao norte e 4,999 km a leste: dentro do raio, perto da borda da caixa.
    north = PointOfInterestFactory(latitude=north_of(4.999)[0], longitude=CENTER[1])
    east_delta = 4.999 / (111.195 * 0.99605)
    east = PointOfInterestFactory(
        latitude=CENTER[0], longitude=round(CENTER[1] + east_delta, 6)
    )

    items = results(
        api_client.get(MAP_URL, {"lat": CENTER[0], "lng": CENTER[1], "radius_km": 5})
    )

    assert {i["id"] for i in items} == {north.pk, east.pk}
