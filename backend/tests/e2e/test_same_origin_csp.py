"""BE-089 — Produção na mesma origem, com a CSP do Nginx, no navegador.

Critério da tarefa: "Dado https://dominio/, então o frontend carrega e
`fetch /api/auth/me/` responde sem CORS". Sem Nginx nesta suíte, um servidor local faz
o papel dele com os MESMOS artefatos que vão para a imagem do proxy:

* o `config.js` de produção (`deploy/nginx/config.prod.js`: API_BASE = origem da página);
* os cabeçalhos dos snippets `security-headers.conf` e `csp-frontend.conf`, lidos dos
  arquivos (mudou a CSP lá, este teste usa a nova);
* `/api/`, `/media/` e `/static/` repassados à API (`live_server`), como o `proxy.conf`.

CORS é DESLIGADO na API (`CORS_ALLOWED_ORIGINS=[]`, `CSRF_TRUSTED_ORIGINS=[]`): qualquer
chamada que dependesse de outra origem falharia. As telas são percorridas como
visitante, cliente e oficina; qualquer violação da CSP, erro de JavaScript, chamada
recusada ou 5xx reprova. O TLS e o próprio Nginx são provados na subida real do CI
(deploy/smoke-test.sh, job deploy-smoke).
"""

import http.client
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from apps.core.tests.world import build_world

from tests.e2e.conftest import FRONTEND, Session

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

DEPLOY = Path(__file__).resolve().parents[3] / "deploy" / "nginx"
PROXIED = ("/api/", "/media/", "/static/", "/admin/")
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "proxy-connection",
}


def nginx_headers(*snippets):
    """`add_header Nome "valor" always;` dos snippets do Nginx, na ordem."""
    pattern = re.compile(r'^\s*add_header\s+(\S+)\s+"([^"]*)"\s+always;', re.M)
    return [
        m.groups()
        for name in snippets
        for m in pattern.finditer((DEPLOY / "snippets" / name).read_text())
    ]


FRONTEND_HEADERS = nginx_headers("security-headers.conf", "csp-frontend.conf")


class _SameOrigin(SimpleHTTPRequestHandler):
    upstream_port = 0

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["X-Forwarded-For"] = self.client_address[0]
        conn = http.client.HTTPConnection("127.0.0.1", self.upstream_port, timeout=30)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read()
        finally:
            conn.close()
        self.send_response(response.status)
        for name, value in response.getheaders():
            if name.lower() not in HOP_BY_HOP and name.lower() != "content-length":
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self):
        if self.path.startswith(PROXIED):
            self._proxy()
            return True
        return False

    def do_GET(self):  # noqa: N802
        if self._route():
            return
        if self.path.split("?", 1)[0] == "/js/config.js":
            body = (DEPLOY / "config.prod.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        if not self._route():
            super().do_HEAD()

    def _write(self):
        if not self._route():
            self.send_error(405)

    do_POST = do_PATCH = do_PUT = do_DELETE = _write  # noqa: N815

    def end_headers(self):
        if not self.path.startswith(PROXIED):
            for name, value in FRONTEND_HEADERS:
                self.send_header(name, value)
        super().end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def origin(live_server):
    from django.test.utils import override_settings

    port = int(live_server.url.rsplit(":", 1)[1])
    handler = partial(
        type("H", (_SameOrigin,), {"upstream_port": port}), directory=str(FRONTEND)
    )
    server = ThreadingHTTPServer(("localhost", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    overrides = override_settings(
        CORS_ALLOWED_ORIGINS=[],
        CSRF_TRUSTED_ORIGINS=[],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
    )
    overrides.enable()
    yield f"http://localhost:{server.server_address[1]}"
    overrides.disable()
    server.shutdown()


CSP_PROBE = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => {
    window.__csp.push(e.violatedDirective + ' ' + (e.blockedURI || 'inline'));
});
"""


# Mensagem de CSP no console: "Content Security Policy" (Chromium) ou
# "Content-Security-Policy" (Firefox).
CSP_CONSOLE = re.compile(r"content[- ]security[- ]policy", re.I)
ABORTED = re.compile(r"ERR_ABORTED|NS_BINDING_ABORTED")


class Browser(Session):
    """Sessão com coleta de violações de CSP e de requisições recusadas."""

    def __init__(self, browser, web, name):
        super().__init__(browser, web, name)
        self.violations = []
        self.refused = []
        self.cross_origin = []
        self.context.add_init_script(CSP_PROBE)
        self.page.on(
            "console",
            lambda m: (
                self.violations.append(f"{name}: {m.text}")
                if CSP_CONSOLE.search(m.text)
                else None
            ),
        )
        # Cancelada pela navegação para a tela seguinte (ex.: o POST /read/ do chat ao
        # sair): ERR_ABORTED no Chromium, NS_BINDING_ABORTED no Firefox. Recusa de
        # CORS/CSP/rede aparece com outro código.
        self.page.on(
            "requestfailed",
            lambda r: (
                self.refused.append(f"{name}: {r.method} {r.url} ({r.failure})")
                if "/api/" in r.url and not ABORTED.search(r.failure or "")
                else None
            ),
        )
        self.page.on(
            "request",
            lambda r: (
                self.cross_origin.append(r.url)
                if "/api/" in r.url and not r.url.startswith(web)
                else None
            ),
        )

    def visit(self, path, ready=None):
        page = self.go(path)
        page.wait_for_load_state("networkidle")
        if ready:
            page.locator(ready).first.wait_for()
        found = page.evaluate("window.__csp")
        self.violations.extend(f"{self.name} {path}: {v}" for v in found)
        assert "não está disponível" not in page.inner_text("body"), (
            f"{path}: servidor indisponível"
        )
        return page

    def problems(self):
        return (
            self.errors
            + self.api_failures
            + self.violations
            + self.refused
            + self.cross_origin
        )


@pytest.fixture
def open_browser(browser, origin):
    opened = []

    def make(name):
        session = Browser(browser, origin, name)
        opened.append(session)
        return session

    yield make
    for session in opened:
        session.close()


def test_frontend_runs_on_the_same_origin_under_the_production_csp(
    open_browser, origin
):
    world = build_world()
    a = world.a

    visitor = open_browser("visitante")
    for path in (
        "index.html",
        "map.html",
        f"shop.html?id={a.workshop.pk}",
        "login.html",
        "register.html",
    ):
        visitor.visit(path)

    client = open_browser("cliente")
    page = client.login(a.client)
    # fetch relativo, sem CORS: a sessão vale porque é a mesma origem.
    status, cors = page.evaluate(
        """async () => {
            const r = await fetch('/api/auth/me/', {credentials: 'include'});
            return [r.status, r.headers.get('access-control-allow-origin')];
        }"""
    )
    assert (status, cors) == (200, None)
    for path in (
        "index.html",
        "map.html",
        f"shop.html?id={a.workshop.pk}",
        "vehicles.html",
        f"vehicle.html?id={a.vehicle.pk}",
        "attendances.html",
        f"attendance.html?id={a.attendance.pk}",
        f"chat.html?id={a.chat.pk}",
        "notifications.html",
        "favorites.html",
        "account.html",
    ):
        client.visit(path)
    # Escrita pela mesma origem: CSRF por cookie + X-CSRFToken, sem origem confiável extra.
    page = client.visit(f"chat.html?id={a.chat.pk}")
    page.fill("#mi", "Mensagem pela mesma origem")
    page.press("#mi", "Enter")
    page.get_by_text("Mensagem pela mesma origem").first.wait_for()

    shop = open_browser("oficina")
    shop.login(a.workshop, "workshop")
    for path in (
        "w-attendances.html",
        f"w-attendance.html?id={a.attendance.pk}",
        f"w-budget.html?id={a.attendance.pk}",
        "w-clients.html",
        "w-services.html",
        "w-products.html",
        "w-promotions.html",
        "w-reviews.html",
        "w-profile.html",
        "workshop-setup.html",
        "notifications.html",
    ):
        shop.visit(path)

    problems = [p for s in (visitor, client, shop) for p in s.problems()]
    assert not problems, "\n".join(problems)


def test_production_config_points_the_api_to_the_page_origin():
    text = (DEPLOY / "config.prod.js").read_text()

    assert "API_BASE: window.location.origin" in text
    assert "DRIVER: 'http'" in text
