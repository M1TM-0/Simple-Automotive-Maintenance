"""BE-094 — Mapa com as duas fontes, no navegador (Chromium e Firefox).

Navegador → API (`live_server`) → **Overpass simulada** por um servidor HTTP local (a
instância pública nunca é usada nos testes) → marcadores no mapa. Prova o que o staging
só consegue provar quando a Overpass pública está de pé:

* estabelecimentos do OpenStreetMap aparecem como losangos, separados das oficinas do
  SAM, sem perfil/chat/favorito/solicitação, com atribuição e link para o OSM;
* a duplicata evidente de uma oficina do SAM não aparece;
* filtros de tipo e texto valem para eles; categoria e "aberto agora" os escondem;
* a caixa "Mostrar … do OpenStreetMap" liga e desliga a camada;
* com a Overpass fora do ar, o aviso aparece e o mapa do SAM continua igual.
"""

import pytest
from apps.workshops.tests.test_overpass import FakeOverpass, node, way
from django.test import override_settings

from tests.e2e.test_flows import _workshop_near

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

# _workshop_near() põe a oficina em (−5,0912; −42,8031).
ELEMENTS = [
    # duplicata evidente da oficina do SAM (mesmo nome, ~30 m)
    node(1, -5.091470, -42.803100, shop="car_repair", name="Auto Center Teste"),
    node(2, -5.090000, -42.802000, amenity="fuel", name="Posto Rio Poty"),
    way(3, -5.092500, -42.804500, shop="tyres", name="Borracharia Teste do Centro"),
]


@pytest.fixture
def overpass(settings):
    fake = FakeOverpass()
    fake.reply = lambda query: (200, {"elements": ELEMENTS})
    with override_settings(
        SAM_OVERPASS={**settings.SAM_OVERPASS, "URL": fake.url, "TIMEOUT_SECONDS": 3}
    ):
        yield fake
    fake.close()


def open_map(session):
    page = session.go("map.html")
    page.locator("#list a.shopc", has_text="Auto Center Teste").wait_for()
    # Um só resultado do SAM: o mapa aproxima (zoom 15) e pede a camada externa.
    page.wait_for_function(
        "() => (t => t !== '' && !t.startsWith('Buscando'))(document.querySelector('#extst').textContent.trim())"
    )
    return page


def osm_pins(page):
    return page.locator(".leaflet-marker-pane .lpin--osm")


def test_openstreetmap_layer_is_shown_apart_from_sam_workshops(sessions, overpass):
    _workshop_near()
    visitor = sessions("visitante")
    page = open_map(visitor)

    assert osm_pins(page).count() == 2  # a duplicata da oficina do SAM não aparece
    assert page.locator(".leaflet-marker-pane .lpin:not(.lpin--osm)").count() == 1
    assert "2 estabelecimentos do OpenStreetMap na área visível" in page.inner_text(
        "#extst"
    )
    # A lista ao lado continua só com o SAM.
    assert page.locator("#list .shopc").count() == 1
    # Atribuição no mapa e na legenda.
    assert "OpenStreetMap contributors" in page.inner_text(
        ".leaflet-control-attribution"
    )
    assert "licença ODbL" in page.inner_text(".mleg")

    page.locator(
        '.leaflet-marker-pane .lpin-w[title="Posto Rio Poty (OpenStreetMap)"]'
    ).click()
    popup = page.locator(".leaflet-popup-content")
    popup.wait_for()
    text = popup.inner_text()
    assert "Posto Rio Poty" in text
    assert "Posto de combustível · não cadastrado no SAM" in text
    assert "OpenStreetMap contributors (ODbL)" in text
    link = popup.locator("a")
    assert link.count() == 1
    assert link.get_attribute("href") == "https://www.openstreetmap.org/node/2"
    assert link.get_attribute("target") == "_blank"
    assert "noopener" in link.get_attribute("rel")
    # Nada das funções exclusivas das oficinas cadastradas.
    assert "Ver perfil" not in text and "shop.html" not in popup.inner_html()

    # A região foi pedida uma vez só (cache por célula no servidor).
    assert len(overpass.queries) == 1


def test_filters_and_toggle_apply_to_the_openstreetmap_layer(sessions, overpass):
    _workshop_near()
    page = open_map(sessions("visitante"))
    assert osm_pins(page).count() == 2

    page.select_option("#ft", "borracharia")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 1"
    )
    page.select_option("#ft", "")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 2"
    )

    # Texto que também acha a oficina do SAM (sem resultado do SAM o mapa volta ao
    # Brasil inteiro e a camada externa some por zoom).
    page.fill("#q", "teste")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 1"
    )
    assert (
        page.locator(
            '.leaflet-marker-pane .lpin-w[title="Borracharia Teste do Centro (OpenStreetMap)"]'
        ).count()
        == 1
    )
    page.fill("#q", "")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 2"
    )

    page.click("#fo")  # "Aberto agora": só oficinas do SAM
    page.wait_for_function(
        "() => document.querySelector('#extst').textContent.includes('valem só para as oficinas')"
    )
    assert osm_pins(page).count() == 0
    page.click("#fo")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 2"
    )

    page.uncheck("#fx")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 0"
    )
    assert page.inner_text("#extst").strip() == ""
    page.check("#fx")
    page.wait_for_function(
        "() => document.querySelectorAll('.leaflet-marker-pane .lpin--osm').length === 2"
    )


def test_overpass_down_keeps_the_sam_map(sessions, overpass):
    overpass.reply = lambda query: (504, b"Gateway Timeout")
    _workshop_near()
    page = open_map(sessions("visitante"))

    assert "indisponíveis no momento" in page.inner_text("#extst")
    assert "As oficinas cadastradas no SAM continuam no mapa" in page.inner_text(
        "#extst"
    )
    assert osm_pins(page).count() == 0
    assert page.locator(".leaflet-marker-pane .lpin:not(.lpin--osm)").count() == 1
    assert page.locator("#list a.shopc", has_text="Auto Center Teste").count() == 1
