#!/usr/bin/env python3
"""Dados de DEMONSTRAÇÃO do staging local (BE-094), criados pela API real.

    python3 deploy/staging/seed_demo.py --base https://sam.localhost \
        --cafile ~/.local/share/sam-staging/ca/ca.pem \
        --accounts ~/.local/share/sam-staging/demo-accounts.json

Cria (idempotente: conta que já existe só faz login e completa o que falta):

* 1 cliente;
* 3 oficinas na região da Av. Paulista (São Paulo) e 1 em Teresina, com ponto no mapa,
  horários e um serviço do catálogo (cadastro concluído → aparecem no mapa público).

Os nomes começam com "[Demonstração]" para não serem confundidos com estabelecimentos
reais. As senhas são aleatórias e ficam só em `--accounts` (0600), fora do repositório.
Usa apenas a biblioteca padrão; o certificado é validado com a CA local (nunca sem
verificação). Nada aqui roda em produção.
"""

import argparse
import http.cookiejar
import json
import os
import secrets
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

WORKSHOPS = [
    {
        "key": "paulista",
        "name_fantasy": "[Demonstração] Oficina Paulista",
        "point": {
            "name": "[Demonstração] Oficina Paulista",
            "type": "oficina",
            "latitude": "-23.561700",
            "longitude": "-46.656200",
            "address": "Av. Paulista (ponto de demonstração), São Paulo - SP",
        },
    },
    {
        "key": "consolacao",
        "name_fantasy": "[Demonstração] Centro Automotivo Consolação",
        "point": {
            "name": "[Demonstração] Centro Automotivo Consolação",
            "type": "centro_automotivo",
            "latitude": "-23.555400",
            "longitude": "-46.660800",
            "address": "Rua da Consolação (ponto de demonstração), São Paulo - SP",
        },
    },
    {
        "key": "bela-vista",
        "name_fantasy": "[Demonstração] Borracharia Bela Vista",
        "point": {
            "name": "[Demonstração] Borracharia Bela Vista",
            "type": "borracharia",
            "latitude": "-23.564300",
            "longitude": "-46.650400",
            "address": "Bela Vista (ponto de demonstração), São Paulo - SP",
        },
    },
    {
        "key": "teresina",
        "name_fantasy": "[Demonstração] Oficina Teresina",
        "point": {
            "name": "[Demonstração] Oficina Teresina",
            "type": "oficina",
            "latitude": "-5.089200",
            "longitude": "-42.801600",
            "address": "Centro (ponto de demonstração), Teresina - PI",
        },
    },
]

HOURS = [
    {"day_of_week": day, "opening_time": "08:00", "closing_time": "18:00"} for day in range(1, 6)
] + [{"day_of_week": 6, "opening_time": "08:00", "closing_time": "12:00"}]


def cnpj(seed: int) -> str:
    """CNPJ numérico válido (dígitos verificadores pelo módulo 11), só para demonstração."""
    base = f"{90000000 + seed:08d}0001"

    def digit(numbers, weights):
        total = sum(int(n) * w for n, w in zip(numbers, weights))
        rest = total % 11
        return "0" if rest < 2 else str(11 - rest)

    first = digit(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = digit(base + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base + first + second


class Api:
    """Uma sessão (cookies próprios) falando com a API pela mesma origem, com CSRF."""

    def __init__(self, base, context):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=context),
        )

    def _csrf(self):
        for cookie in self.jar:
            if cookie.name == "csrftoken":
                return cookie.value
        return ""

    def call(self, method, path, body=None, expect=(200, 201, 204)):
        if method != "GET" and not self._csrf():
            self.call("GET", "/api/auth/me/", expect=(200, 401))
        headers = {"Accept": "application/json", "Origin": self.base, "Referer": self.base + "/"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if method != "GET":
            headers["X-CSRFToken"] = self._csrf()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        payload = json.loads(raw) if raw else None
        if status not in expect:
            raise RuntimeError(f"{method} {path} → {status}: {raw[:300]!r}")
        return status, payload


def login_or_register(api, role, email, password, register_body):
    status, _ = api.call(
        "POST", "/api/auth/login/", {"role": role, "email": email, "password": password}, expect=(200, 400, 401, 403)
    )
    if status == 200:
        return "existente"
    api.call("POST", "/api/auth/register/", {"role": role, "email": email, "password": password, **register_body})
    return "criada"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", required=True)
    parser.add_argument("--cafile", required=True)
    parser.add_argument("--accounts", required=True, type=Path)
    args = parser.parse_args()

    context = ssl.create_default_context(cafile=args.cafile)  # verificação ligada
    accounts = json.loads(args.accounts.read_text()) if args.accounts.exists() else {}
    accounts.setdefault("client", {"email": "demo-cliente@sam.localhost", "password": secrets.token_urlsafe(12)})
    for index, shop in enumerate(WORKSHOPS, start=1):
        accounts.setdefault(
            shop["key"],
            {"email": f"demo-{shop['key']}@sam.localhost", "password": secrets.token_urlsafe(12), "cnpj": cnpj(index)},
        )
    args.accounts.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o077)
    try:
        args.accounts.write_text(json.dumps(accounts, indent=2, ensure_ascii=False) + "\n")
    finally:
        os.umask(old_umask)
    args.accounts.chmod(0o600)

    client = accounts["client"]
    result = login_or_register(
        Api(args.base, context), "client", client["email"], client["password"], {"name": "Cliente Demonstração"}
    )
    print(f"cliente {client['email']}: {result}")

    catalog = Api(args.base, context).call("GET", "/api/services/?q=oleo")[1]["results"]
    if not catalog:
        catalog = Api(args.base, context).call("GET", "/api/services/")[1]["results"]
    service_id = catalog[0]["id"]

    for shop in WORKSHOPS:
        account = accounts[shop["key"]]
        api = Api(args.base, context)
        result = login_or_register(
            api,
            "workshop",
            account["email"],
            account["password"],
            {"name_fantasy": shop["name_fantasy"], "name_responsible": "Responsável Demonstração", "cnpj": account["cnpj"]},
        )
        api.call("PUT", "/api/workshop/operation-hours/", HOURS)
        me = api.call("GET", "/api/workshop/me/")[1]
        if not (me.get("point_of_interest") or me.get("point")):
            api.call("POST", "/api/workshop/point/", shop["point"])
        services = api.call("GET", "/api/workshop/services/")[1]
        if not services.get("count"):
            api.call(
                "POST",
                "/api/workshop/services/",
                {"id_service": service_id, "price_base": "150.00", "duration_estimate": 60},
            )
        api.call("PATCH", "/api/workshop/page/", {"description": "Oficina de DEMONSTRAÇÃO do staging local do SAM."})
        print(f"oficina {shop['name_fantasy']}: {result}")

    visible = Api(args.base, context).call("GET", "/api/map/points/?q=demonstra")[1]
    print(f"no mapa público: {visible['count']} oficinas de demonstração")
    print(f"contas e senhas: {args.accounts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
