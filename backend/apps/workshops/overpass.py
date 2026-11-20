"""Estabelecimentos externos do OpenStreetMap pela Overpass API (BE-094, ADR 0010).

Segunda fonte do mapa, **complementar** às oficinas e pontos do SAM (`/map/points/`):
postos de combustível, borracharias, oficinas e lojas que não estão cadastrados no
SAM. São só exibidos (nome, tipo, posição, endereço e link para o OSM): não têm perfil,
chat, favorito, solicitação de atendimento nem avaliação.

Como a consulta é feita (política de uso da Overpass pública):

* **Só a região visível**, e só com zoom suficiente: a caixa pedida é coberta por
  células de `CELL_DEGREES` (≈ 5,5 km); acima de `MAX_CELLS` a resposta é
  `too_large` e nada é consultado (o frontend pede para aproximar o mapa).
* **Cache por célula** (`CACHE_SECONDS`, padrão 24 h, no cache do Django — em produção o
  `DatabaseCache`, compartilhado por todos os processos): mover o mapa reaproveita as
  células já buscadas; só as que faltam vão numa **única** consulta.
* **Orçamento global** de consultas por minuto (`MAX_REQUESTS_PER_MINUTE`) e **recuo
  exponencial** depois de falha, 429 ou 5xx (de `BACKOFF_SECONDS` até
  `MAX_BACKOFF_SECONDS`): durante o recuo só o cache responde.
* **Tempo limite** curto (`TIMEOUT_SECONDS`) e resposta limitada a `MAX_RESPONSE_BYTES`.
  Qualquer falha vira `status = unavailable`/`partial` **com HTTP 200**: o mapa continua
  mostrando as oficinas do SAM, que vêm de outro endpoint e não dependem daqui.

Licença: dados do OpenStreetMap, ODbL 1.0 — atribuição "© OpenStreetMap contributors"
junto do mapa (o frontend mostra; a resposta também traz `attribution` e `license`).
Só se guardam no cache os campos exibidos; nada é gravado nas tabelas do SAM.
"""

import json
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("sam.overpass")

CELL_DEGREES = 0.05
CACHE_VERSION = 1  # muda se o formato guardado no cache mudar
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE = "ODbL 1.0"
LICENSE_URL = "https://www.openstreetmap.org/copyright"
SOURCE = "OpenStreetMap (Overpass API)"

# (chave, valor, tipo do SAM), na ordem de prioridade: um elemento com duas etiquetas
# (ex.: posto com lava-jato) recebe o tipo da primeira que bater.
OSM_CATEGORIES = (
    ("amenity", "fuel", "posto_combustivel"),
    ("shop", "tyres", "borracharia"),
    ("shop", "car_repair", "oficina"),
    ("shop", "car_parts", "loja_autopecas"),
    ("amenity", "car_wash", "lava_jato"),
    ("shop", "repair", "outro"),
)

TYPE_LABELS = {
    "posto_combustivel": "Posto de combustível",
    "borracharia": "Borracharia",
    "oficina": "Oficina",
    "loja_autopecas": "Loja de autopeças",
    "lava_jato": "Lava-jato",
    "outro": "Reparos",
}

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_UNAVAILABLE = "unavailable"
STATUS_TOO_LARGE = "too_large"
STATUS_DISABLED = "disabled"

MESSAGES = {
    STATUS_PARTIAL: (
        "Parte dos estabelecimentos do OpenStreetMap não pôde ser carregada agora. "
        "As oficinas cadastradas no SAM continuam no mapa."
    ),
    STATUS_UNAVAILABLE: (
        "Os estabelecimentos do OpenStreetMap estão indisponíveis no momento. "
        "As oficinas cadastradas no SAM continuam no mapa."
    ),
    STATUS_TOO_LARGE: "Aproxime o mapa para ver postos, borracharias e oficinas do OpenStreetMap.",
    STATUS_DISABLED: "A busca de estabelecimentos do OpenStreetMap está desligada neste ambiente.",
}

_COOLDOWN_KEY = "sam:overpass:cooldown"
_BACKOFF_KEY = "sam:overpass:backoff"
_BUDGET_KEY = "sam:overpass:budget:{minute}"


class OverpassError(Exception):
    """Falha ao consultar a Overpass (rede, tempo, HTTP ou resposta inválida)."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


@dataclass
class ExternalResult:
    status: str
    results: list = field(default_factory=list)
    cells_total: int = 0
    cells_from_cache: int = 0
    cells_fetched: int = 0

    @property
    def detail(self):
        return MESSAGES.get(self.status, "")


def config():
    defaults = {
        "URL": "",
        "TIMEOUT_SECONDS": 12,
        "QUERY_TIMEOUT_SECONDS": 10,
        "CACHE_SECONDS": 24 * 3600,
        "MAX_CELLS": 16,
        "MAX_REQUESTS_PER_MINUTE": 10,
        "BACKOFF_SECONDS": 60,
        "MAX_BACKOFF_SECONDS": 900,
        "MAX_RESPONSE_BYTES": 5 * 1024 * 1024,
        "USER_AGENT": "SAM-Simple-Automotive-Maintenance/1.0 (projeto academico)",
    }
    return {**defaults, **getattr(settings, "SAM_OVERPASS", {})}


# ------------------------------------------------------------------ células


def cells_for(south, west, north, east):
    """Células (i, j) que cobrem a caixa. i = faixa de latitude, j = de longitude."""
    i0, i1 = math.floor(south / CELL_DEGREES), math.floor(north / CELL_DEGREES)
    j0, j1 = math.floor(west / CELL_DEGREES), math.floor(east / CELL_DEGREES)
    return [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]


def cell_count(south, west, north, east):
    rows = math.floor(north / CELL_DEGREES) - math.floor(south / CELL_DEGREES) + 1
    cols = math.floor(east / CELL_DEGREES) - math.floor(west / CELL_DEGREES) + 1
    return rows * cols


def cell_bounds(cell):
    i, j = cell
    return (
        round(i * CELL_DEGREES, 6),
        round(j * CELL_DEGREES, 6),
        round((i + 1) * CELL_DEGREES, 6),
        round((j + 1) * CELL_DEGREES, 6),
    )


def cell_of(lat, lng):
    return (math.floor(lat / CELL_DEGREES), math.floor(lng / CELL_DEGREES))


def _cell_key(cell):
    return f"sam:overpass:v{CACHE_VERSION}:cell:{cell[0]}:{cell[1]}"


# ------------------------------------------------------------------ consulta


def build_query(south, west, north, east, timeout):
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    selectors = "".join(
        f'nwr["{key}"="{value}"]({bbox});' for key, value, _ in OSM_CATEGORIES
    )
    return f"[out:json][timeout:{int(timeout)}];({selectors});out center tags qt;"


def _fetch(south, west, north, east, conf):
    """Uma consulta à Overpass. Devolve a lista `elements` ou levanta OverpassError."""
    if not str(conf["URL"]).startswith(("https://", "http://")):
        raise OverpassError("SAM_OVERPASS_URL precisa começar com https:// ou http://")
    query = build_query(south, west, north, east, conf["QUERY_TIMEOUT_SECONDS"])
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(
        conf["URL"],
        data=body,
        method="POST",
        headers={
            "User-Agent": conf["USER_AGENT"],
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    limit = conf["MAX_RESPONSE_BYTES"]
    timeout = conf["TIMEOUT_SECONDS"]
    try:
        # URL da configuração, com esquema conferido acima.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise OverpassError(f"HTTP {exc.code}", status=exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise OverpassError(f"rede: {reason}") from None
    if len(raw) > limit:
        raise OverpassError(f"resposta acima de {limit} bytes")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise OverpassError("resposta não é JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise OverpassError("resposta sem 'elements'")
    remark = str(payload.get("remark") or "")
    # Tempo ou memória esgotados no servidor: os elementos vêm incompletos (não cachear).
    if "runtime error" in remark.lower() or "timed out" in remark.lower():
        raise OverpassError(f"consulta incompleta: {remark[:200]}")
    return payload["elements"]


# ------------------------------------------------------------------ normalização

_SPACES = re.compile(r"\s+")


def _clean(value, limit=255):
    text = _SPACES.sub(" ", str(value or "")).strip()
    return text[:limit]


def _category(tags):
    for key, value, sam_type in OSM_CATEGORIES:
        if tags.get(key) == value:
            return sam_type, f"{key}={value}"
    return None, None


def _address(tags):
    street = _clean(tags.get("addr:street"))
    number = _clean(tags.get("addr:housenumber"), 20)
    district = _clean(tags.get("addr:suburb") or tags.get("addr:neighbourhood"))
    city = _clean(tags.get("addr:city"))
    first = ", ".join(part for part in (street, number) if part)
    rest = ", ".join(part for part in (district, city) if part)
    text = " — ".join(part for part in (first, rest) if part)
    return text[:500] or None


def normalize_element(element):
    """Elemento da Overpass → ponto externo (ou None se não servir para o mapa)."""
    kind = element.get("type")
    osm_id = element.get("id")
    if kind not in ("node", "way", "relation") or not isinstance(osm_id, int):
        return None
    if kind == "node":
        lat, lng = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") or {}
        lat, lng = center.get("lat"), center.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    tags = element.get("tags") or {}
    sam_type, osm_tag = _category(tags)
    if sam_type is None:
        return None
    name = _clean(tags.get("name") or tags.get("brand") or tags.get("operator"))
    return {
        "id": f"osm:{kind}:{osm_id}",
        "osm_type": kind,
        "osm_id": osm_id,
        "name": name or f"{TYPE_LABELS[sam_type]} (sem nome no OpenStreetMap)",
        "has_name": bool(name),
        "type": sam_type,
        "osm_tag": osm_tag,
        "lat": round(float(lat), 6),
        "lng": round(float(lng), 6),
        "address": _address(tags),
        "osm_url": f"https://www.openstreetmap.org/{kind}/{osm_id}",
    }


# ------------------------------------------------------------------ duplicatas com o SAM

# Palavras que não distinguem um estabelecimento de outro ("Auto Center Silva" ×
# "Silva Pneus" comparam só "silva").
_GENERIC_WORDS = frozenset(
    "auto autos posto oficina mecanica mecanico centro center automotivo automotiva car cars "
    "borracharia pneus pneu servicos servico service ltda me eireli epp sa de da do das dos e "
    "em the shop loja pecas autopecas lava jato rede".split()
)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
SAME_PLACE_METERS = 5
NEARBY_METERS = 100
_GRID = 0.002


def _plain(text):
    from apps.core.search import normalize_search_text

    return _NON_ALNUM.sub(" ", normalize_search_text(text)).strip()


def _words(text):
    """Palavras normalizadas; iniciais soltas viram uma palavra ("J.R." → "jr")."""
    words, initials = [], ""
    for word in _plain(text).split():
        if len(word) == 1:
            initials += word
            continue
        if initials:
            words.append(initials)
            initials = ""
        words.append(word)
    if initials:
        words.append(initials)
    return words


def _tokens(text):
    return {w for w in _words(text) if len(w) > 1 and w not in _GENERIC_WORDS}


def similar_names(a, b):
    """Mesmo estabelecimento pelo nome, olhando só as palavras distintivas (sem "auto",
    "posto", "pneus"…): uma sequência contém a outra (≥ 4 letras) ou as palavras
    coincidem em pelo menos metade (Jaccard ≥ 0,5). Nome só com palavras genéricas
    ("Borracharia") não prova nada."""
    tokens_a, tokens_b = _tokens(a), _tokens(b)
    if not tokens_a or not tokens_b:
        return False
    core_a = "".join(w for w in _words(a) if w in tokens_a)
    core_b = "".join(w for w in _words(b) if w in tokens_b)
    if min(len(core_a), len(core_b)) >= 4 and (core_a in core_b or core_b in core_a):
        return True
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b) >= 0.5


def _osm_ids(point):
    """Formas aceitas em `external_id` de um ponto importado do OSM: `node/123`, `n123`."""
    return {
        f"{point['osm_type']}/{point['osm_id']}",
        f"{point['osm_type'][0]}{point['osm_id']}",
    }


def drop_sam_duplicates(points, sam_points):
    """Remove do resultado externo o que já está no SAM (`sam_points`: dicts com `lat`,
    `lng`, `names` e, se importado, `external_source`/`external_id`).

    Duplicata evidente = mesmo id do OSM num ponto importado (`import_pois` com fonte
    `osm…`); ou praticamente o mesmo lugar (≤ 5 m); ou perto (≤ 100 m) com nome
    parecido com o do ponto ou o da oficina vinculada.
    """
    from apps.workshops.geo import haversine_km

    imported = {
        str(p.get("external_id"))
        for p in sam_points
        if str(p.get("external_source") or "").lower().startswith("osm")
        and p.get("external_id")
    }
    # Grade de 0,002° (≥ 100 m até ~60° de latitude): cada ponto externo só é comparado
    # com os do SAM na própria célula e nas vizinhas.
    grid = {}
    for sam in sam_points:
        grid.setdefault(
            (math.floor(sam["lat"] / _GRID), math.floor(sam["lng"] / _GRID)), []
        ).append(sam)

    kept = []
    for point in points:
        if imported & _osm_ids(point):
            continue
        gi, gj = math.floor(point["lat"] / _GRID), math.floor(point["lng"] / _GRID)
        near = [
            s
            for di in (-1, 0, 1)
            for dj in (-1, 0, 1)
            for s in grid.get((gi + di, gj + dj), ())
        ]
        duplicate = False
        for sam in near:
            meters = 1000 * haversine_km(
                point["lat"], point["lng"], sam["lat"], sam["lng"]
            )
            if meters <= SAME_PLACE_METERS:
                duplicate = True
            elif meters <= NEARBY_METERS and point["has_name"]:
                duplicate = any(
                    similar_names(point["name"], name) for name in sam["names"] if name
                )
            if duplicate:
                break
        if not duplicate:
            kept.append(point)
    return kept


# ------------------------------------------------------------------ limites e recuo


def _in_cooldown():
    return cache.get(_COOLDOWN_KEY) is not None


def _start_cooldown(conf, reason):
    previous = cache.get(_BACKOFF_KEY) or 0
    seconds = min(
        conf["MAX_BACKOFF_SECONDS"], max(conf["BACKOFF_SECONDS"], previous * 2)
    )
    cache.set(_COOLDOWN_KEY, reason, seconds)
    # Lembra o último recuo por mais tempo que ele mesmo: falhas seguidas dobram.
    cache.set(_BACKOFF_KEY, seconds, seconds * 4)
    logger.warning(
        "Overpass indisponível (%s); só o cache responde pelos próximos %s s.",
        reason,
        seconds,
        extra={
            "event": "overpass.unavailable",
            "reason": reason,
            "backoff_seconds": seconds,
        },
    )


def _take_budget(conf):
    """Reserva uma consulta no orçamento do minuto atual (todos os processos)."""
    key = _BUDGET_KEY.format(minute=int(time.time() // 60))
    cache.add(key, 0, 120)
    try:
        used = cache.incr(key)
    except ValueError:  # a chave expirou entre o add e o incr
        cache.set(key, 1, 120)
        used = 1
    return used <= conf["MAX_REQUESTS_PER_MINUTE"]


# ------------------------------------------------------------------ ponto de entrada


def external_points(south, west, north, east):
    """Estabelecimentos do OSM dentro da caixa (já validada: south < north, west < east)."""
    conf = config()
    if not conf["URL"]:
        return ExternalResult(STATUS_DISABLED)
    total = cell_count(south, west, north, east)
    if total > conf["MAX_CELLS"]:
        return ExternalResult(STATUS_TOO_LARGE, cells_total=total)

    cells = cells_for(south, west, north, east)
    keys = {cell: _cell_key(cell) for cell in cells}
    cached = cache.get_many(list(keys.values()))
    found = {cell: cached[key] for cell, key in keys.items() if key in cached}
    missing = [cell for cell in cells if cell not in found]
    fetched = 0

    if missing and not _in_cooldown():
        if _take_budget(conf):
            box = (
                min(cell_bounds(c)[0] for c in missing),
                min(cell_bounds(c)[1] for c in missing),
                max(cell_bounds(c)[2] for c in missing),
                max(cell_bounds(c)[3] for c in missing),
            )
            try:
                elements = _fetch(*box, conf)
            except OverpassError as exc:
                _start_cooldown(conf, str(exc))
            else:
                cache.delete(_BACKOFF_KEY)
                per_cell = {cell: [] for cell in missing}
                for element in elements:
                    point = normalize_element(element)
                    if point is None:
                        continue
                    cell = cell_of(point["lat"], point["lng"])
                    if cell in per_cell:
                        per_cell[cell].append(point)
                cache.set_many(
                    {keys[c]: pts for c, pts in per_cell.items()}, conf["CACHE_SECONDS"]
                )
                found.update(per_cell)
                fetched = len(missing)
                logger.info(
                    "Overpass: %s células consultadas, %s elementos.",
                    len(missing),
                    len(elements),
                    extra={
                        "event": "overpass.fetch",
                        "cells": len(missing),
                        "elements": len(elements),
                    },
                )
        else:
            logger.warning(
                "Overpass: orçamento de consultas do minuto esgotado; só o cache responde.",
                extra={"event": "overpass.budget"},
            )

    results = [
        point
        for cell in cells
        for point in found.get(cell, ())
        if south <= point["lat"] <= north and west <= point["lng"] <= east
    ]
    if len(found) == len(cells):
        status = STATUS_OK
    elif found:
        status = STATUS_PARTIAL
    else:
        status = STATUS_UNAVAILABLE
    return ExternalResult(
        status,
        results=results,
        cells_total=len(cells),
        cells_from_cache=len(cells) - len(missing),
        cells_fetched=fetched,
    )
