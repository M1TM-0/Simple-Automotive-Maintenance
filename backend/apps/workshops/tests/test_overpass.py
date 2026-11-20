"""BE-094 — estabelecimentos do OpenStreetMap (Overpass API) no mapa, ADR 0010.

A Overpass é simulada por um servidor HTTP local de verdade (mesmo caminho de rede que
em produção: POST, tempo limite, códigos HTTP, JSON inválido); a instância pública nunca
é consultada pelos testes.
"""

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from apps.core.tests.factories import PointOfInterestFactory
from apps.workshops import overpass
from apps.workshops.tests.test_public_api import make_public_workshop

URL = "/api/map/external-points/"
# Uma célula de 0,05° em Teresina (−5,10…−5,05 × −42,85…−42,80).
BOX = {"south": -5.095, "west": -42.845, "north": -5.055, "east": -42.805}


def node(osm_id, lat, lng, **tags):
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lng, "tags": tags}


def way(osm_id, lat, lng, **tags):
    return {
        "type": "way",
        "id": osm_id,
        "center": {"lat": lat, "lon": lng},
        "tags": tags,
    }


class FakeOverpass:
    """Servidor local no lugar da Overpass. `reply` decide a resposta de cada POST."""

    def __init__(self):
        self.queries = []
        self.reply = lambda query: (200, {"elements": []})
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 — nome da API do http.server
                length = int(self.headers.get("Content-Length") or 0)
                form = urllib.parse.parse_qs(self.rfile.read(length).decode())
                query = form.get("data", [""])[0]
                fake.queries.append(
                    {"query": query, "user_agent": self.headers.get("User-Agent")}
                )
                status, body = fake.reply(query)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # o cliente desistiu (teste de tempo limite)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/interpreter"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake(settings):
    server = FakeOverpass()
    settings.SAM_OVERPASS = {
        **settings.SAM_OVERPASS,
        "URL": server.url,
        "TIMEOUT_SECONDS": 2,
        "BACKOFF_SECONDS": 60,
        "MAX_BACKOFF_SECONDS": 900,
        "MAX_REQUESTS_PER_MINUTE": 10,
        "MAX_CELLS": 16,
    }
    yield server
    server.close()


def get(api_client, **params):
    return api_client.get(URL, {**BOX, **params})


def bbox_of(query):
    """(south, west, north, east) do primeiro seletor da consulta enviada."""
    inside = query.split("(", 2)[2].split(")", 1)[0]
    return tuple(float(x) for x in inside.split(","))


# ------------------------------------------------------------------ resposta normal


@pytest.mark.django_db
class TestExternalPoints:
    def test_points_inside_the_box_are_normalized_with_attribution(
        self, api_client, fake
    ):
        fake.reply = lambda q: (
            200,
            {
                "elements": [
                    node(
                        1,
                        -5.08,
                        -42.82,
                        amenity="fuel",
                        name="Posto Rio Poty",
                        brand="Ipiranga",
                    ),
                    way(
                        2,
                        -5.07,
                        -42.83,
                        shop="tyres",
                        **{
                            "addr:street": "Rua A",
                            "addr:housenumber": "10",
                            "addr:city": "Teresina",
                        },
                    ),
                    node(3, -5.06, -42.81, shop="car_repair", name="Mecânica do Zé"),
                    node(
                        4, -5.06, -42.81, amenity="bank", name="Banco"
                    ),  # fora das categorias
                    node(
                        5, -5.20, -42.81, amenity="fuel", name="Longe"
                    ),  # fora da célula
                ]
            },
        )

        response = get(api_client)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["detail"] == ""
        assert body["attribution"] == "© OpenStreetMap contributors"
        assert body["license"] == "ODbL 1.0"
        assert body["license_url"] == "https://www.openstreetmap.org/copyright"
        assert response["Cache-Control"] == "public, max-age=300"
        by_id = {p["id"]: p for p in body["results"]}
        assert set(by_id) == {"osm:node:1", "osm:way:2", "osm:node:3"}
        assert body["count"] == 3
        fuel = by_id["osm:node:1"]
        assert fuel == {
            "id": "osm:node:1",
            "osm_type": "node",
            "osm_id": 1,
            "name": "Posto Rio Poty",
            "has_name": True,
            "type": "posto_combustivel",
            "osm_tag": "amenity=fuel",
            "lat": -5.08,
            "lng": -42.82,
            "address": None,
            "osm_url": "https://www.openstreetmap.org/node/1",
        }
        tyres = by_id["osm:way:2"]
        assert tyres["type"] == "borracharia"
        assert tyres["has_name"] is False
        assert tyres["name"] == "Borracharia (sem nome no OpenStreetMap)"
        assert tyres["address"] == "Rua A, 10 — Teresina"
        assert tyres["osm_url"] == "https://www.openstreetmap.org/way/2"
        assert by_id["osm:node:3"]["type"] == "oficina"

    def test_query_asks_for_the_osm_categories_inside_the_cell_and_identifies_the_app(
        self, api_client, fake
    ):
        get(api_client)

        assert len(fake.queries) == 1
        query = fake.queries[0]["query"]
        for tag in (
            '"amenity"="fuel"',
            '"shop"="car_repair"',
            '"shop"="tyres"',
            '"shop"="repair"',
            '"shop"="car_parts"',
            '"amenity"="car_wash"',
        ):
            assert f"nwr[{tag}]" in query
        assert query.startswith("[out:json][timeout:10];")
        assert query.endswith("out center tags qt;")
        assert bbox_of(query) == (-5.1, -42.85, -5.05, -42.8)
        assert "SAM" in fake.queries[0]["user_agent"]

    def test_second_request_is_served_from_the_cache(self, api_client, fake):
        fake.reply = lambda q: (
            200,
            {"elements": [node(1, -5.08, -42.82, amenity="fuel", name="P")]},
        )

        first = get(api_client).json()
        second = get(api_client).json()

        assert len(fake.queries) == 1
        assert second["results"] == first["results"]
        assert second["status"] == "ok"

    def test_panning_fetches_only_the_missing_cells_in_one_query(
        self, api_client, fake
    ):
        get(api_client)  # célula (−5,10…−5,05; −42,85…−42,80)

        # Caixa que cobre a célula já buscada e a vizinha a leste.
        get(api_client, east=-42.78)

        assert len(fake.queries) == 2
        assert bbox_of(fake.queries[1]["query"]) == (-5.1, -42.8, -5.05, -42.75)

    def test_empty_cells_are_cached_too(self, api_client, fake):
        get(api_client)
        get(api_client)

        assert len(fake.queries) == 1


# ------------------------------------------------------------------ falhas da Overpass


@pytest.mark.django_db
class TestOverpassFailures:
    @pytest.mark.parametrize("status", [429, 502, 503, 504, 400])
    def test_http_error_answers_200_unavailable_and_not_cached(
        self, api_client, fake, status
    ):
        fake.reply = lambda q: (status, b"at capacity")

        response = get(api_client)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "unavailable"
        assert body["results"] == []
        assert "As oficinas cadastradas no SAM continuam no mapa" in body["detail"]
        assert response["Cache-Control"] == "no-store"

    def test_backoff_after_failure_keeps_the_service_alone(self, api_client, fake):
        fake.reply = lambda q: (504, b"timeout")
        get(api_client)
        get(api_client)
        get(api_client, east=-42.78)

        assert len(fake.queries) == 1  # recuo: nada vai à Overpass
        assert overpass.cache.get("sam:overpass:backoff") == 60

        # Fim do recuo; nova falha dobra o próximo.
        overpass.cache.delete("sam:overpass:cooldown")
        get(api_client)
        assert len(fake.queries) == 2
        assert overpass.cache.get("sam:overpass:backoff") == 120

        # Volta ao normal: sucesso zera o recuo.
        overpass.cache.delete("sam:overpass:cooldown")
        fake.reply = lambda q: (200, {"elements": []})
        assert get(api_client).json()["status"] == "ok"
        assert overpass.cache.get("sam:overpass:backoff") is None

    def test_slow_overpass_hits_the_timeout(self, api_client, fake, settings):
        settings.SAM_OVERPASS = {**settings.SAM_OVERPASS, "TIMEOUT_SECONDS": 0.5}

        def slow(q):
            time.sleep(2)
            return 200, {"elements": []}

        fake.reply = slow
        started = time.monotonic()

        body = get(api_client).json()

        assert time.monotonic() - started < 1.8
        assert body["status"] == "unavailable"

    def test_unreachable_server(self, api_client, settings):
        settings.SAM_OVERPASS = {
            **settings.SAM_OVERPASS,
            "URL": "http://127.0.0.1:9/api/interpreter",
            "TIMEOUT_SECONDS": 2,
        }

        assert get(api_client).json()["status"] == "unavailable"

    @pytest.mark.parametrize(
        "body",
        [
            b"<html>not json</html>",
            {"no": "elements"},
            {
                "elements": [],
                "remark": 'runtime error: Query timed out in "query" at line 1',
            },
        ],
        ids=["html", "sem-elements", "consulta-incompleta"],
    )
    def test_invalid_or_incomplete_answer_is_not_cached(self, api_client, fake, body):
        fake.reply = lambda q: (200, body)

        assert get(api_client).json()["status"] == "unavailable"
        overpass.cache.delete("sam:overpass:cooldown")
        fake.reply = lambda q: (200, {"elements": []})
        assert get(api_client).json()["status"] == "ok"
        assert len(fake.queries) == 2

    def test_oversized_answer_is_refused(self, api_client, fake, settings):
        settings.SAM_OVERPASS = {**settings.SAM_OVERPASS, "MAX_RESPONSE_BYTES": 100}
        fake.reply = lambda q: (
            200,
            {"elements": [node(i, -5.08, -42.82, amenity="fuel") for i in range(50)]},
        )

        assert get(api_client).json()["status"] == "unavailable"

    def test_partial_when_some_cells_are_cached(self, api_client, fake):
        fake.reply = lambda q: (
            200,
            {"elements": [node(1, -5.08, -42.82, amenity="fuel", name="P")]},
        )
        get(api_client)
        fake.reply = lambda q: (504, b"timeout")

        body = get(api_client, east=-42.78).json()

        assert body["status"] == "partial"
        assert [p["id"] for p in body["results"]] == ["osm:node:1"]
        assert "Parte dos estabelecimentos" in body["detail"]

    def test_budget_per_minute_protects_the_public_instance(
        self, api_client, fake, settings
    ):
        settings.SAM_OVERPASS = {**settings.SAM_OVERPASS, "MAX_REQUESTS_PER_MINUTE": 1}

        assert get(api_client).json()["status"] == "ok"
        body = get(api_client, south=-4.995, north=-4.955).json()  # outra célula

        assert body["status"] == "unavailable"
        assert len(fake.queries) == 1

    def test_sam_map_keeps_working_with_overpass_down(self, api_client, fake):
        fake.reply = lambda q: (502, b"at capacity")
        workshop = make_public_workshop("Oficina SAM", coords=(-5.08, -42.82))

        assert get(api_client).json()["status"] == "unavailable"
        sam = api_client.get("/api/map/points/").json()["results"]

        assert [(p["kind"], p["id"]) for p in sam] == [("workshop", workshop.pk)]


# ------------------------------------------------------------------ região e validação


@pytest.mark.django_db
class TestRegion:
    def test_large_region_is_refused_without_querying(self, api_client, fake):
        body = get(api_client, south=-5.5, north=-4.5, west=-43.3, east=-42.3).json()

        assert body["status"] == "too_large"
        assert body["results"] == []
        assert "Aproxime o mapa" in body["detail"]
        assert fake.queries == []

    def test_disabled_when_url_is_empty(self, api_client, settings):
        settings.SAM_OVERPASS = {**settings.SAM_OVERPASS, "URL": ""}

        body = get(api_client).json()

        assert body["status"] == "disabled"
        assert body["results"] == []

    def test_non_http_url_is_refused(self, api_client, settings):
        settings.SAM_OVERPASS = {**settings.SAM_OVERPASS, "URL": "file:///etc/passwd"}

        assert get(api_client).json()["status"] == "unavailable"

    @pytest.mark.parametrize(
        "params, field",
        [
            ({"south": None}, "south"),
            ({"north": -5.2}, "north"),
            ({"east": -42.9}, "east"),
            ({"south": -91}, "south"),
            ({"east": 181}, "east"),
            ({"west": "abc"}, "west"),
        ],
    )
    def test_invalid_box_is_400(self, api_client, fake, params, field):
        query = {**BOX, **params}
        query = {k: v for k, v in query.items() if v is not None}

        response = api_client.get(URL, query)

        assert response.status_code == 400
        assert field in response.json()
        assert fake.queries == []

    def test_rate_limit_per_ip(self, api_client, fake, monkeypatch):
        from apps.core.throttles import ExternalMapRateThrottle

        monkeypatch.setattr(
            ExternalMapRateThrottle, "THROTTLE_RATES", {"external_map": "2/min"}
        )

        assert get(api_client).status_code == 200
        assert get(api_client).status_code == 200
        response = get(api_client)

        assert response.status_code == 429
        assert "Retry-After" in response


# ------------------------------------------------------------------ duplicatas com o SAM


@pytest.mark.django_db
class TestDeduplication:
    def test_evident_duplicates_of_sam_points_are_removed(self, api_client, fake):
        make_public_workshop("Auto Center Silva", coords=(-5.080000, -42.820000))
        PointOfInterestFactory(
            name="Posto importado",
            latitude=-5.070000,
            longitude=-42.830000,
            type="posto_combustivel",
            external_source="osm-2026-11",
            external_id="node/20",
        )
        PointOfInterestFactory(
            name="Borracharia Central", latitude=-5.060000, longitude=-42.810000
        )
        fake.reply = lambda q: (
            200,
            {
                "elements": [
                    # mesmo lugar da oficina do SAM (≈ 1 m), nome diferente
                    node(
                        10, -5.080005, -42.820005, shop="car_repair", name="Outro nome"
                    ),
                    # ≈ 55 m da oficina, nome parecido
                    node(
                        11,
                        -5.080500,
                        -42.820000,
                        shop="car_repair",
                        name="Silva Auto Center",
                    ),
                    # importado do OSM com o mesmo id, em outro lugar
                    node(20, -5.075000, -42.835000, amenity="fuel", name="Posto"),
                    # ≈ 55 m do ponto "Borracharia Central", nome parecido
                    way(
                        30,
                        -5.060500,
                        -42.810000,
                        shop="tyres",
                        name="Borracharia Central Pneus",
                    ),
                    # ≈ 55 m da oficina, nome diferente → outro estabelecimento
                    node(
                        40, -5.079500, -42.820000, amenity="fuel", name="Posto Ipiranga"
                    ),
                    # ≈ 55 m, sem nome → não dá para afirmar que é o mesmo
                    node(50, -5.080000, -42.820500, shop="tyres"),
                    # longe de tudo
                    node(
                        60,
                        -5.090000,
                        -42.840000,
                        shop="car_parts",
                        name="Autopeças Silva",
                    ),
                ]
            },
        )

        body = get(api_client).json()

        assert sorted(p["id"] for p in body["results"]) == [
            "osm:node:40",
            "osm:node:50",
            "osm:node:60",
        ]
        assert body["count"] == 3

    def test_point_of_a_non_public_workshop_also_counts(self, api_client, fake):
        make_public_workshop(
            "Oficina Bloqueada", coords=(-5.08, -42.82), status="blocked"
        )
        fake.reply = lambda q: (
            200,
            {"elements": [node(1, -5.08, -42.82, shop="car_repair", name="X")]},
        )

        assert get(api_client).json()["results"] == []


# ------------------------------------------------------------------ funções puras


class TestPure:
    @pytest.mark.parametrize(
        "a, b, expected",
        [
            ("Posto Shell", "Shell Select", True),
            ("Auto Mecânica Silva", "Silva Pneus", True),
            ("Oficina do Zé", "Posto Ipiranga", False),
            ("Borracharia", "Borracharia", False),  # nome só genérico não prova nada
            ("Mecânica Irmãos Souza", "Souza Irmãos", True),
            ("Centro Automotivo Alfa", "Alfa", True),
            ("Auto", "Auto Posto", False),  # só palavras genéricas, curtas
            ("", "Qualquer", False),
            ("JR Pneus", "J.R. Pneus e Serviços", True),
        ],
    )
    def test_similar_names(self, a, b, expected):
        assert overpass.similar_names(a, b) is expected

    def test_cells_cover_the_box(self):
        cells = overpass.cells_for(-5.095, -42.845, -5.055, -42.805)

        assert cells == [(-102, -857)]
        assert overpass.cell_bounds(cells[0]) == (-5.1, -42.85, -5.05, -42.8)
        assert overpass.cell_count(-5.095, -42.845, -4.955, -42.705) == 9

    @pytest.mark.parametrize(
        "element",
        [
            {"type": "node", "id": 1, "lat": 1, "lon": 2, "tags": {"amenity": "bank"}},
            {"type": "node", "id": 1, "tags": {"amenity": "fuel"}},
            {"type": "way", "id": 1, "tags": {"amenity": "fuel"}},
            {
                "type": "node",
                "id": "x",
                "lat": 1,
                "lon": 2,
                "tags": {"amenity": "fuel"},
            },
            {"type": "area", "id": 1, "lat": 1, "lon": 2, "tags": {"amenity": "fuel"}},
            {"type": "node", "id": 1, "lat": 99, "lon": 2, "tags": {"amenity": "fuel"}},
        ],
    )
    def test_unusable_elements_are_dropped(self, element):
        assert overpass.normalize_element(element) is None

    def test_type_priority_and_name_fallbacks(self):
        both = overpass.normalize_element(
            node(1, 0, 0, amenity="fuel", shop="car_repair", brand="BR")
        )
        repair = overpass.normalize_element(
            node(2, 0, 0, shop="repair", operator="Fulano")
        )

        assert (both["type"], both["osm_tag"], both["name"]) == (
            "posto_combustivel",
            "amenity=fuel",
            "BR",
        )
        assert (repair["type"], repair["name"], repair["has_name"]) == (
            "outro",
            "Fulano",
            True,
        )
