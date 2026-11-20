"""Infraestrutura dos testes ponta a ponta (BE-082): frontend real → API → banco.

* API: `live_server` do pytest-django (Django de verdade numa thread, banco de teste
  PostgreSQL com o `init.sql`; dados criados pelas fábricas ficam visíveis porque os
  testes são transacionais).
* Frontend: os arquivos de `frontend/` servidos por um servidor HTTP local; só o
  `js/config.js` é reescrito para apontar `API_BASE` para o `live_server`
  (`DRIVER: 'http'`). Mesmo host (`localhost`), portas diferentes — como em dev (DP-21).
* Navegadores (BE-094): **Chromium e Firefox** do Playwright — cada teste roda nos dois
  (`[chromium]`/`[firefox]` no nome); WebKit fora do escopo. Um contexto limpo por
  perfil (cookies próprios). Tiles do OpenStreetMap são bloqueados (o mapa funciona sem
  eles; não se consome o serviço público nos testes). Erros de JavaScript da página
  reprovam o teste.

Rodar: `pytest -m e2e` (navegadores com `python -m playwright install chromium firefox`).
`SAM_E2E_BROWSERS=chromium` (ou `firefox`) restringe; `SAM_E2E_CHROMIUM` /
`SAM_E2E_FIREFOX` apontam outro binário. Falhas deixam a captura de tela em
`backend/e2e-artifacts/` (com o navegador no nome).

Se as telas aparecem sem nenhum texto (altura 0, `innerText` vazio), o fontconfig do
Chromium não entende a configuração de fontes da distribuição: aponte um arquivo mínimo
com `FONTCONFIG_FILE=/caminho/fonts.conf` (`<dir>/usr/share/fonts</dir>` + `<cachedir>`).
"""

import functools
import os
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")


BACKEND = Path(__file__).resolve().parents[2]
FRONTEND = BACKEND.parent / "frontend"
ARTIFACTS = BACKEND / "e2e-artifacts"
PASSWORD = (
    "SenhaTeste123"  # senha das contas das fábricas (apps/core/tests/factories.py)
)
TIMEOUT = 15_000


class _FrontendHandler(SimpleHTTPRequestHandler):
    api_base = ""

    def do_GET(self):  # noqa: N802 — nome da API do http.server
        if self.path.split("?", 1)[0] == "/js/config.js":
            body = (
                "window.SAM = Object.assign(window.SAM || {}, "
                f"{{ config: {{ API_BASE: '{self.api_base}', DRIVER: 'http' }} }});"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def web(live_server):
    """Origem do frontend (ex.: http://localhost:41234) servindo `frontend/`."""
    api_base = live_server.url.replace("127.0.0.1", "localhost")
    handler = functools.partial(
        type("H", (_FrontendHandler,), {"api_base": api_base}), directory=str(FRONTEND)
    )
    server = ThreadingHTTPServer(("localhost", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://localhost:{server.server_address[1]}"

    from django.test.utils import override_settings

    overrides = override_settings(
        CORS_ALLOWED_ORIGINS=[origin],
        CSRF_TRUSTED_ORIGINS=[origin],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        FRONTEND_BASE_URL=origin,
    )
    overrides.enable()
    yield origin
    overrides.disable()
    server.shutdown()


SUPPORTED_BROWSERS = ("chromium", "firefox")
BROWSERS = [
    name.strip()
    for name in os.environ.get("SAM_E2E_BROWSERS", ",".join(SUPPORTED_BROWSERS)).split(
        ","
    )
    if name.strip()
]
assert set(BROWSERS) <= set(SUPPORTED_BROWSERS), (
    f"SAM_E2E_BROWSERS inválido: {BROWSERS}"
)


@pytest.fixture(scope="session", params=BROWSERS)
def browser(request):
    # O Playwright síncrono roda um loop asyncio na thread do teste e o ORM das fábricas é
    # síncrono: libera só enquanto o navegador existe (não vaza para o resto da sessão,
    # nem para o `check --deploy`, que recusa a variável — async.E001).
    previous = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    try:
        yield from _launch(request.param)
    finally:
        if previous is None:
            os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
        else:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = previous


def _launch(name):
    with playwright_api.sync_playwright() as p:
        launch = {"headless": True}
        binary = os.environ.get(f"SAM_E2E_{name.upper()}")
        if binary:
            launch["executable_path"] = binary
        instance = getattr(p, name).launch(**launch)
        yield instance
        instance.close()


class Session:
    """Um perfil no navegador (contexto próprio: cookies e localStorage separados)."""

    def __init__(self, browser, web, name):
        self.web, self.name = web, name
        self.context = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="pt-BR"
        )
        self.context.set_default_timeout(TIMEOUT)
        self.context.route(
            re.compile(r"https://[a-z.]*tile\.openstreetmap\.org/.*"),
            lambda route: route.abort(),
        )
        self.page = self.context.new_page()
        self.errors = []
        self.api_failures = []
        self.page.on("pageerror", lambda exc: self.errors.append(f"{name}: {exc}"))
        self.page.on(
            "response",
            lambda r: (
                self.api_failures.append(f"{r.request.method} {r.url} → {r.status}")
                if "/api/" in r.url and r.status >= 500
                else None
            ),
        )

    def go(self, path):
        self.page.goto(f"{self.web}/{path}")
        return self.page

    def login(self, account, role="client", password=PASSWORD):
        page = self.go("login.html")
        if role == "workshop":
            page.locator(
                "label", has=page.locator("input[name=role][value=workshop]")
            ).click()
        page.fill("#email", account.email)
        page.fill("#pw", password)
        page.click("#sb")
        page.wait_for_url(lambda url: "login.html" not in url)
        return page

    def close(self):
        self.context.close()


@pytest.fixture
def sessions(browser, web, request):
    opened = []

    def open_session(name="cliente"):
        session = Session(browser, web, name)
        opened.append(session)
        return session

    yield open_session

    failed = getattr(request.node, "rep_call", None) and request.node.rep_call.failed
    ARTIFACTS.mkdir(exist_ok=True)
    for session in opened:
        if failed:
            session.page.screenshot(
                path=str(ARTIFACTS / f"{_safe(request.node.name)}-{session.name}.png"),
                full_page=True,
            )
        session.close()
    errors = [e for s in opened for e in s.errors + s.api_failures]
    if not failed:
        assert not errors, "erros no navegador ou 5xx da API:\n" + "\n".join(errors)


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
