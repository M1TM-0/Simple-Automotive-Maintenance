"""Importa pontos de interesse do mapa (borracharias, postos, lojas…) — BE-071, DP-10.

    python manage.py import_pois --file pontos.csv --source osm-2026-11 [--dry-run]
    python manage.py import_pois --file pontos.geojson --source osm-2026-11

**Idempotente** pela chave `(external_source, external_id)` (`uq_poi_external`):
reimportar o mesmo arquivo não cria nada novo; uma linha cujo ponto já existe
atualiza nome, tipo, coordenadas e endereço. Ponto **vinculado a uma oficina**
não é alterado (a oficina confirmou aquele ponto; ver `POST /workshop/point/`).

**Licença.** Só são gravados nome, tipo, coordenadas, endereço e o identificador
na fonte — confira os termos de uso da fonte antes de importar (comentário do
`init.sql`). Atribuições exigidas pela fonte vão na interface do mapa, não aqui.

Formatos (pela extensão, ou `--format`):

- **CSV** (UTF-8, cabeçalho): `external_id,name,type,latitude,longitude,address`
  e, opcional, `external_source` (por linha; senão vale `--source`).
- **GeoJSON** `FeatureCollection` de `Point` (`coordinates = [lng, lat]`); o id
  vem de `properties.external_id` ou do `id` da feature; os demais campos de
  `properties`.

`type` é um valor de TYPE_ESTABLISHMENT (`oficina`, `borracharia`,
`posto_combustivel`, `loja_autopecas`, `centro_automotivo`, `concessionaria`,
`lava_jato`, `outro`). Linhas inválidas são rejeitadas e listadas no relatório
(número da linha/feature e motivo); as válidas são gravadas. `--dry-run` valida e
conta tudo dentro de uma transação desfeita no fim: nada é gravado.
"""

import csv
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from apps.workshops.models import EstablishmentType, PointOfInterest
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

COORDINATE_PLACES = Decimal("0.000001")
MAX_NAME = 255
MAX_ADDRESS = 500
MAX_SOURCE = 50
MAX_EXTERNAL_ID = 255
VALID_TYPES = {value for value, _ in EstablishmentType.choices}
UPDATABLE = ("name", "type", "latitude", "longitude", "address")


class _Rollback(Exception):
    """Desfaz a transação do `--dry-run`."""


class RowError(ValueError):
    pass


@dataclass
class Report:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    claimed: int = 0
    rejected: list = field(default_factory=list)

    @property
    def total(self):
        return (
            self.created
            + self.updated
            + self.unchanged
            + self.claimed
            + len(self.rejected)
        )


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _coordinate(raw, limit, label) -> Decimal:
    try:
        value = Decimal(_text(raw).replace(",", "."))
    except InvalidOperation:
        raise RowError(f"{label} inválida: {raw!r}.") from None
    if not value.is_finite() or not -limit <= value <= limit:
        raise RowError(f"{label} fora do intervalo (−{limit} a {limit}): {raw}.")
    return value.quantize(COORDINATE_PLACES, rounding=ROUND_HALF_UP)


def clean_row(raw: dict, default_source: str | None) -> dict:
    """Valida e normaliza uma linha. Erros viram `RowError` com mensagem em pt-BR."""
    source = _text(raw.get("external_source")) or (default_source or "")
    external_id = _text(raw.get("external_id"))
    if source and not external_id:
        raise RowError(
            "external_id ausente (origem e identificador vão sempre juntos)."
        )
    if external_id and not source:
        raise RowError(
            "external_source ausente: informe --source ou a coluna external_source."
        )
    if not source:
        raise RowError(
            "Sem origem e identificador: a importação precisa da chave para ser idempotente."
        )
    if len(source) > MAX_SOURCE:
        raise RowError(f"external_source com mais de {MAX_SOURCE} caracteres.")
    if len(external_id) > MAX_EXTERNAL_ID:
        raise RowError(f"external_id com mais de {MAX_EXTERNAL_ID} caracteres.")

    name = " ".join(_text(raw.get("name")).split())
    if not name:
        raise RowError("Nome ausente.")
    if len(name) > MAX_NAME:
        raise RowError(f"Nome com mais de {MAX_NAME} caracteres.")

    kind = _text(raw.get("type")).lower()
    if kind not in VALID_TYPES:
        raise RowError(
            f"Tipo inválido: {raw.get('type')!r} (use {', '.join(sorted(VALID_TYPES))})."
        )

    address = " ".join(_text(raw.get("address")).split()) or None
    if address and len(address) > MAX_ADDRESS:
        raise RowError(f"Endereço com mais de {MAX_ADDRESS} caracteres.")

    return {
        "external_source": source,
        "external_id": external_id,
        "name": name,
        "type": kind,
        "latitude": _coordinate(raw.get("latitude"), 90, "Latitude"),
        "longitude": _coordinate(raw.get("longitude"), 180, "Longitude"),
        "address": address,
    }


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"external_id", "name", "type", "latitude", "longitude"} - set(
            reader.fieldnames or []
        )
        if missing:
            raise CommandError(
                f"Cabeçalho do CSV sem as colunas: {', '.join(sorted(missing))}."
            )
        for line, row in enumerate(reader, start=2):  # linha 1 = cabeçalho
            yield f"linha {line}", row


def read_geojson(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"GeoJSON inválido: {exc}") from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise CommandError("O GeoJSON precisa ser uma FeatureCollection.")
    for index, feature in enumerate(data.get("features") or [], start=1):
        where = f"feature {index}"
        if not isinstance(feature, dict):
            yield where, {"_error": "Feature inválida."}
            continue
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if (
            geometry.get("type") != "Point"
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            yield where, {"_error": "Geometria precisa ser um Point [lng, lat]."}
            continue
        properties = dict(feature.get("properties") or {})
        properties.setdefault("external_id", feature.get("id"))
        properties["longitude"], properties["latitude"] = coordinates[0], coordinates[1]
        yield where, properties


class Command(BaseCommand):
    help = "Importa pontos de interesse (CSV ou GeoJSON) de forma idempotente (BE-071)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", required=True, help="Arquivo .csv ou .geojson/.json."
        )
        parser.add_argument(
            "--source",
            help="Origem (external_source, até 50 caracteres) aplicada às linhas sem a coluna.",
        )
        parser.add_argument(
            "--format", choices=("csv", "geojson"), help="Força o formato do arquivo."
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Valida e conta, sem gravar nada."
        )

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"Arquivo não encontrado: {path}")
        source = _text(options.get("source")) or None
        if source and len(source) > MAX_SOURCE:
            raise CommandError(f"--source com mais de {MAX_SOURCE} caracteres.")
        fmt = options.get("format") or (
            "csv" if path.suffix.lower() == ".csv" else "geojson"
        )
        rows = read_csv(path) if fmt == "csv" else read_geojson(path)

        report = Report()
        try:
            with transaction.atomic():
                self._import(rows, source, report)
                if options["dry_run"]:
                    raise _Rollback
        except _Rollback:
            pass

        self._print(report, dry_run=options["dry_run"])

    def _import(self, rows, default_source, report):
        seen = set()
        for where, raw in rows:
            try:
                if "_error" in raw:
                    raise RowError(raw["_error"])
                data = clean_row(raw, default_source)
                key = (data["external_source"], data["external_id"])
                if key in seen:
                    raise RowError(f"Identificador repetido no arquivo: {key[1]}.")
                seen.add(key)
                self._upsert(data, report)
            except RowError as exc:
                report.rejected.append((where, str(exc)))
            except (
                DatabaseError
            ) as exc:  # regra do banco: rejeita a linha, segue com as outras
                report.rejected.append(
                    (where, f"Recusada pelo banco: {exc}".splitlines()[0])
                )

    def _upsert(self, data, report):
        with transaction.atomic():  # savepoint: erro do banco desfaz só esta linha
            point = (
                PointOfInterest.objects.select_for_update()
                .filter(
                    external_source=data["external_source"],
                    external_id=data["external_id"],
                )
                .first()
            )
            if point is None:
                PointOfInterest.objects.create(**data)
                report.created += 1
                return
            if _claimed(point):
                report.claimed += 1
                return
            changed = [name for name in UPDATABLE if getattr(point, name) != data[name]]
            if not changed:
                report.unchanged += 1
                return
            for name in changed:
                setattr(point, name, data[name])
            point.save(update_fields=changed)
            report.updated += 1

    def _print(self, report, *, dry_run):
        prefix = "[simulação — nada foi gravado] " if dry_run else ""
        self.stdout.write(
            f"{prefix}linhas: {report.total} | criados: {report.created} | atualizados: {report.updated} | "
            f"sem mudança: {report.unchanged} | vinculados a oficina (preservados): {report.claimed} | "
            f"rejeitados: {len(report.rejected)}"
        )
        for where, reason in report.rejected:
            self.stdout.write(f"  rejeitada ({where}): {reason}")


def _claimed(point) -> bool:
    from apps.accounts.models import Workshop

    return Workshop.objects.filter(point_of_interest=point).exists()
