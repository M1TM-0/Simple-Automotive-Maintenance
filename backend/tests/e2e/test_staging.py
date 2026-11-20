"""BE-094 — Validação no staging LOCAL (https://sam.localhost), em Chromium e Firefox.

Diferente do resto de `tests/e2e/` (frontend real + API no `live_server`), aqui o alvo é
o staging no ar — Nginx com TLS, Gunicorn, PostgreSQL próprio, OSM de verdade:

* HTTPS **validado** pela CA local (sem `ignore_https_errors`): cada navegador recebe um
  banco de certificados próprio só com a CA do staging (Chromium: `$HOME/.pki/nssdb`
  temporário; Firefox: perfil temporário). Controle negativo: sem a CA, a página é
  recusada (prova de que a validação está ligada).
* Mapa: tiles do OpenStreetMap carregados (com Referer = origem, exigido pela política de
  uso do OSM), atribuição visível, oficinas do SAM e a camada do OpenStreetMap
  (Overpass) — ou, se a Overpass estiver fora do ar, o aviso e o mapa do SAM intactos.
* Fluxos essenciais com as contas de demonstração (`staging.sh seed`).

Rodar (staging no ar; ver backend/docs/STAGING.md):

    SAM_STAGING_URL=https://sam.localhost venv/bin/pytest -m staging

`SAM_STAGING_HOME` (padrão ~/.local/share/sam-staging) tem a CA e as contas.
`SAM_STAGING_EXPECT_OVERPASS=up|down` exige o estado da Overpass (padrão: aceita os dois
e registra); `down` roda também o ensaio de indisponibilidade (`staging.sh overpass`).
Evidências de cada navegador em `backend/e2e-artifacts/staging-<navegador>.json`.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import ARTIFACTS, BROWSERS

playwright_api = pytest.importorskip("playwright.sync_api")

STAGING = os.environ.get("SAM_STAGING_URL", "").rstrip("/")
HOME = Path(
    os.environ.get("SAM_STAGING_HOME", "~/.local/share/sam-staging")
).expanduser()
CA = HOME / "ca" / "ca.pem"
ACCOUNTS = HOME / "demo-accounts.json"
EXPECT_OVERPASS = os.environ.get("SAM_STAGING_EXPECT_OVERPASS", "any")
TIMEOUT = 20_000
SAO_PAULO = {"latitude": -23.5605, "longitude": -46.6560}
TERESINA = {"latitude": -5.0892, "longitude": -42.8016}
SP_SHOPS = (
    "[Demonstração] Oficina Paulista",
    "[Demonstração] Centro Automotivo Consolação",
    "[Demonstração] Borracharia Bela Vista",
)

pytestmark = [
    pytest.mark.staging,
    pytest.mark.skipif(
        not STAGING, reason="SAM_STAGING_URL não definido (staging no ar?)"
    ),
]


def _nssdb(directory: Path):
    """Banco NSS novo com a CA do staging confiável para sites (C,,)."""
    if shutil.which("certutil") is None:
        pytest.fail("certutil (pacote nss) é necessário para confiar na CA local")
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["certutil", "-N", "-d", f"sql:{directory}", "--empty-password"], check=True
    )
    subprocess.run(
        [
            "certutil",
            "-A",
            "-d",
            f"sql:{directory}",
            "-t",
            "C,,",
            "-n",
            "SAM staging local CA",
            "-i",
            str(CA),
        ],
        check=True,
    )


class Staging:
    """Um navegador (Chromium ou Firefox) que confia só na CA do staging."""

    def __init__(self, playwright, name, tmp, trust=True):
        self.name = name
        self.errors = []
        options = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "pt-BR",
            "permissions": ["geolocation"],
            "geolocation": SAO_PAULO,
        }
        binary = os.environ.get(f"SAM_E2E_{name.upper()}")
        launch = {"headless": True, **({"executable_path": binary} if binary else {})}
        if name == "chromium":
            home = tmp / "home"
            if trust:
                _nssdb(home / ".pki" / "nssdb")
            home.mkdir(exist_ok=True)
            self.browser = playwright.chromium.launch(
                env={**os.environ, "HOME": str(home)}, **launch
            )
            self.context = self.browser.new_context(**options)
        else:
            profile = tmp / "profile"
            if trust:
                _nssdb(profile)
            profile.mkdir(exist_ok=True)
            self.browser = None
            self.context = playwright.firefox.launch_persistent_context(
                str(profile), **launch, **options
            )
        self.context.set_default_timeout(TIMEOUT)

    def page(self):
        page = self.context.new_page()
        page.on("pageerror", lambda exc: self.errors.append(f"pageerror: {exc}"))
        page.on(
            "response",
            lambda r: (
                self.errors.append(f"{r.status} {r.url}")
                if "/api/" in r.url and r.status >= 500
                else None
            ),
        )
        return page

    def close(self):
        self.context.close()
        if self.browser:
            self.browser.close()


@pytest.fixture(scope="module")
def playwright():
    with playwright_api.sync_playwright() as p:
        yield p


@pytest.fixture(scope="module", params=BROWSERS)
def staging(request, playwright, tmp_path_factory):
    browser = Staging(playwright, request.param, tmp_path_factory.mktemp(request.param))
    yield browser
    browser.close()


@pytest.fixture(scope="module")
def evidence(staging):
    record = {"browser": staging.name, "url": STAGING}
    yield record
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / f"staging-{staging.name}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False)
    )


def accounts():
    return json.loads(ACCOUNTS.read_text())


def login(page, email, password, role="client"):
    page.goto(f"{STAGING}/login.html")
    if role == "workshop":
        page.locator(
            "label", has=page.locator("input[name=role][value=workshop]")
        ).click()
    page.fill("#email", email)
    page.fill("#pw", password)
    page.click("#sb")
    page.wait_for_url(lambda url: "login.html" not in url)


# ------------------------------------------------------------------ HTTPS


def test_https_is_trusted_through_the_local_ca(staging, evidence):
    page = staging.page()

    response = page.goto(f"{STAGING}/")

    assert response.ok
    details = response.security_details() or {}
    evidence["tls"] = details
    assert details.get("protocol") in ("TLS 1.3", "TLS 1.2")
    assert "SAM staging local CA" in (details.get("issuer") or "")
    assert (details.get("subjectName") or "") == "sam.localhost"
    # HTTP vai para HTTPS.
    redirected = page.goto(STAGING.replace("https://", "http://") + "/map.html")
    assert redirected.url == f"{STAGING}/map.html"
    page.close()


def test_without_the_local_ca_the_browser_refuses_the_site(
    playwright, tmp_path, staging
):
    """Controle negativo: a validação do certificado está ligada de verdade."""
    untrusted = Staging(playwright, staging.name, tmp_path, trust=False)
    try:
        with pytest.raises(playwright_api.Error) as error:
            untrusted.page().goto(f"{STAGING}/")
    finally:
        untrusted.close()
    assert re.search(
        r"CERT_AUTHORITY_INVALID|SEC_ERROR_UNKNOWN_ISSUER|certificate",
        str(error.value),
        re.I,
    )


# ------------------------------------------------------------------ mapa


def _open_map_near(staging, where):
    staging.context.set_geolocation(where)
    page = staging.page()
    tiles = []
    page.on(
        "requestfinished",
        lambda r: (
            tiles.append(
                {
                    "url": r.url,
                    "referer": r.all_headers().get("referer"),
                    "status": r.response().status,
                }
            )
            if "tile.openstreetmap.org" in r.url
            else None
        ),
    )
    page.goto(f"{STAGING}/map.html")
    page.locator("#list .shopc").first.wait_for()
    with page.expect_response(
        lambda r: "/api/map/external-points/" in r.url, timeout=40_000
    ) as external:
        page.click("#gb")
        page.get_by_text("Usando sua localização").wait_for()
    return page, tiles, external.value


def test_map_tiles_attribution_sam_workshops_and_openstreetmap_layer(staging, evidence):
    page, tiles, external = _open_map_near(staging, SAO_PAULO)
    body = external.json()

    # Oficinas do SAM: as três de São Paulo, na lista e como pinos em gota.
    for name in SP_SHOPS:
        page.locator("#list a.shopc", has_text=name).wait_for()
    assert page.locator("#list a.shopc", has_text="Teresina").count() == 0
    sam_pins = page.locator(".leaflet-marker-pane .lpin:not(.lpin--osm)").count()
    assert sam_pins >= 3

    # Tiles do OpenStreetMap carregados, com Referer = origem do staging.
    page.wait_for_function(
        """() => [...document.querySelectorAll('img.leaflet-tile-loaded')]
            .some(i => i.src.startsWith('https://tile.openstreetmap.org/') && i.naturalWidth === 256)"""
    )
    page.wait_for_load_state("networkidle")
    assert tiles, "nenhum tile do OpenStreetMap foi pedido"
    assert all(t["referer"] == f"{STAGING}/" for t in tiles), tiles[:3]
    ok_tiles = [t for t in tiles if t["status"] == 200]
    # A política do OSM bloqueia sem Referer (resposta 403 com um tile de aviso).
    assert len(ok_tiles) == len(tiles), [t for t in tiles if t["status"] != 200][:3]

    # Atribuição: controle do Leaflet e legenda.
    attribution = page.locator(".leaflet-control-attribution")
    assert "OpenStreetMap contributors" in attribution.inner_text()
    assert (
        attribution.locator('a[href="https://www.openstreetmap.org/copyright"]').count()
        >= 1
    )
    assert "licença ODbL" in page.locator(".mleg").inner_text()

    # Camada do OpenStreetMap (Overpass).
    status = body["status"]
    page.wait_for_function(
        "() => (t => t !== '' && !t.startsWith('Buscando'))(document.querySelector('#extst').textContent.trim())"
    )
    message = page.locator("#extst").inner_text()
    osm_pins = page.locator(".leaflet-marker-pane .lpin--osm").count()
    evidence["map"] = {
        "sam_workshops_listed": len(SP_SHOPS),
        "sam_pins": sam_pins,
        "osm_tiles_requested": len(tiles),
        "osm_tiles_200": len(ok_tiles),
        "tile_referer": tiles[0]["referer"],
        "zoom": page.evaluate(
            "() => document.querySelector('.leaflet-tile-loaded').src.split('/')[3]"
        ),
        "external_status": status,
        "external_count": body["count"],
        "external_attribution": body["attribution"],
        "osm_pins": osm_pins,
        "status_message": message,
    }
    if EXPECT_OVERPASS != "any":
        assert status == ("ok" if EXPECT_OVERPASS == "up" else "unavailable"), body
    if status in ("ok", "partial") and body["count"]:
        assert osm_pins == body["count"]
        assert "do OpenStreetMap na área visível" in message
        pin = page.locator(".leaflet-marker-pane .lpin-w:has(.lpin--osm)").first
        pin.click()
        popup = page.locator(".leaflet-popup-content")
        popup.wait_for()
        text = popup.inner_text()
        evidence["map"]["osm_popup"] = text
        assert "não cadastrado no SAM" in text
        assert "OpenStreetMap contributors (ODbL)" in text
        assert popup.locator('a[href^="https://www.openstreetmap.org/"]').count() == 1
        # Nada exclusivo das oficinas cadastradas: sem perfil, chat, favorito, solicitação.
        assert popup.locator('a[href*="shop.html"]').count() == 0
        assert "Ver perfil" not in text
    elif status in ("unavailable", "partial"):
        assert "As oficinas cadastradas no SAM continuam no mapa" in message
    assert not staging.errors, staging.errors
    page.close()


@pytest.mark.skipif(
    EXPECT_OVERPASS != "down",
    reason="ensaio de indisponibilidade: SAM_STAGING_EXPECT_OVERPASS=down",
)
def test_overpass_down_keeps_the_sam_map_working(staging, evidence):
    page, _, external = _open_map_near(staging, TERESINA)
    body = external.json()

    page.locator("#list a.shopc", has_text="[Demonstração] Oficina Teresina").wait_for()
    assert page.locator(".leaflet-marker-pane .lpin:not(.lpin--osm)").count() >= 1
    assert body["status"] == "unavailable" and body["results"] == []
    page.wait_for_function(
        "() => document.querySelector('#extst').textContent.includes('indisponíveis')"
    )
    assert page.locator(".leaflet-marker-pane .lpin--osm").count() == 0
    evidence["overpass_down"] = {
        "external_status": body["status"],
        "status_message": page.locator("#extst").inner_text(),
        "sam_listed": page.locator("#list a.shopc").count(),
        "response_ms": external.request.timing.get("responseEnd"),
    }
    assert not staging.errors, staging.errors
    page.close()


# ------------------------------------------------------------------ fluxos essenciais


def test_client_login_map_profile_favorite_and_pages(staging, evidence):
    client = accounts()["client"]
    page = staging.page()
    login(page, client["email"], client["password"])

    page.goto(f"{STAGING}/map.html")
    page.locator("#list a.shopc", has_text="[Demonstração] Oficina Paulista").click()
    page.wait_for_url("**/shop.html?id=*")
    page.get_by_text("Oficina de DEMONSTRAÇÃO do staging local do SAM.").wait_for()

    # Escrita pela mesma origem (sessão + CSRF): favoritar e desfazer.
    button = page.locator("#bf")
    before = button.get_attribute("aria-pressed")
    after = "false" if before == "true" else "true"
    button.click()
    page.wait_for_selector(f'#bf[aria-pressed="{after}"]')
    button.click()
    page.wait_for_selector(f'#bf[aria-pressed="{before}"]')

    for path in (
        "vehicles.html",
        "attendances.html",
        "favorites.html",
        "notifications.html",
        "account.html",
    ):
        page.goto(f"{STAGING}/{path}")
        page.wait_for_load_state("networkidle")
        assert "não está disponível" not in page.inner_text("body"), path
    evidence["client_flow"] = "login → mapa → perfil → favoritar/desfazer → 5 telas"
    assert not staging.errors, staging.errors
    page.close()
    staging.context.clear_cookies()


def test_workshop_login_and_panel(staging, evidence):
    shop = accounts()["paulista"]
    page = staging.page()
    login(page, shop["email"], shop["password"], role="workshop")

    for path in (
        "w-attendances.html",
        "w-services.html",
        "w-profile.html",
        "w-reviews.html",
    ):
        page.goto(f"{STAGING}/{path}")
        page.wait_for_load_state("networkidle")
        assert "não está disponível" not in page.inner_text("body"), path
    evidence["workshop_flow"] = "login → atendimentos, serviços, perfil, avaliações"
    assert not staging.errors, staging.errors
    page.close()
    staging.context.clear_cookies()
