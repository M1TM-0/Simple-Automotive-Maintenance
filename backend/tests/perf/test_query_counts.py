"""BE-083 — Sem N+1: o número de consultas de cada leitura não cresce com o volume.

Para **toda** operação GET do schema (as listagens e detalhes do contrato, sem código
por rota), mede as consultas com o mundo de teste já com itens em toda lista,
multiplica os dados do lado A (`grow_side`) e mede de novo: precisa ser igual. Também há um teto absoluto por
requisição (`MAX_QUERIES`) para pegar regressões grosseiras.
"""

import contextlib
from unittest import mock

import pytest
from apps.core.tests.world import build_world, grow_side
from apps.workshops import overpass
from conftest import open_account_session
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from tests.security.test_authz_matrix import operations, values_for

pytestmark = pytest.mark.django_db

MAX_QUERIES = 15
# Rotas com parâmetros obrigatórios na query string (BE-094): a caixa visível do mapa,
# com 16 células (o máximo) em volta do mundo de teste, e uma Overpass simulada com
# pontos dentro dela (para medir também a consulta de duplicatas no banco).
EXTERNAL = "/api/map/external-points/"
QUERY = {EXTERNAL: "?south=-5.15&west=-42.85&north=-5.0&east=-42.70"}
ELEMENTS = [
    {
        "type": "node",
        "id": i,
        "lat": -5.09 + i / 1000,
        "lon": -42.80,
        "tags": {"amenity": "fuel"},
    }
    for i in range(1, 6)
]
READS = [
    op
    for op in operations()
    if op.method == "GET" and not op.path.startswith("/api/health/")
]


def _actor(op, world, django_user_model):
    if "client" in op.allowed:
        return "client", open_account_session(world.a.client, "client")
    if "workshop" in op.allowed:
        return "workshop", open_account_session(world.a.workshop, "workshop")
    if "admin" in op.allowed:
        api = APIClient()
        api.force_login(
            django_user_model.objects.create_user(
                "mod", "mod@exemplo.com", "x" * 12, is_staff=True
            )
        )
        return "admin", api
    return None, APIClient()


def _count(api, url):
    with CaptureQueriesContext(connection) as queries:
        response = api.get(url)
    assert response.status_code == 200, (
        f"{url}: {response.status_code} {response.content[:200]!r}"
    )
    return len(queries)


def _external_source(op, settings):
    if op.path != EXTERNAL:
        return contextlib.nullcontext()
    settings.SAM_OVERPASS = {
        **settings.SAM_OVERPASS,
        "URL": "https://overpass.test/api",
    }
    return mock.patch.object(overpass, "_fetch", return_value=ELEMENTS)


@pytest.mark.parametrize("op", READS, ids=str)
def test_query_count_does_not_grow_with_data(op, django_user_model, settings):
    world = build_world()
    role, api = _actor(op, world, django_user_model)
    url = op.url(
        values_for(op, world, "A", role if role in ("client", "workshop") else None)
    ) + QUERY.get(op.path, "")

    with _external_source(op, settings):
        grow_side(
            world.a, n=1
        )  # toda lista já começa com itens (consultas fixas por página)
        api.get(url)  # aquece caches de sessão/ContentType
        before = _count(api, url)
        grow_side(world.a, n=3)
        after = _count(api, url)

    assert after == before, f"{op.key}: {before} → {after} consultas (N+1)"
    assert before <= MAX_QUERIES, f"{op.key}: {before} consultas por requisição"
