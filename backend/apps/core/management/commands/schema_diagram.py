"""Gera docs/DIAGRAMA_SAM.svg a partir do banco migrado (BE-093).

    python manage.py schema_diagram [--output CAMINHO]

O diagrama físico sai do próprio PostgreSQL (tabelas, colunas e tipos, PK, FK, valores
permitidos dos status por CHECK e ENUM, views), então confere com o `init.sql` e as
migrations por construção. `tests/deploy/test_artifacts.py` gera de novo e compara com
o arquivo versionado: mudou o schema, rode este comando e commite o SVG.
"""

import re
from collections import defaultdict
from html import escape
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

SAM_APPS = (
    "accounts",
    "workshops",
    "catalog",
    "vehicles",
    "attendances",
    "chat",
    "reviews",
    "promotions",
    "notifications",
    "core",
)
MODULE_TITLES = {
    "accounts": "Contas e favoritos",
    "workshops": "Oficina e mapa",
    "catalog": "Catálogo e produtos",
    "vehicles": "Veículos e histórico",
    "attendances": "Atendimento e orçamento",
    "chat": "Chat",
    "reviews": "Avaliações e denúncias",
    "promotions": "Promoções e divulgações",
    "notifications": "Notificações",
    "core": "Operação",
}
COLORS = {
    "accounts": "#d9485f",
    "workshops": "#e07b39",
    "catalog": "#c9a227",
    "vehicles": "#4f9d69",
    "attendances": "#2f80c0",
    "chat": "#5b6ad0",
    "reviews": "#9b59b6",
    "promotions": "#c2549b",
    "notifications": "#2a9d8f",
    "core": "#6c757d",
}
TYPE_ABBREVIATIONS = (
    ("character varying", "varchar"),
    ("timestamp with time zone", "timestamptz"),
    ("time without time zone", "time"),
    ("double precision", "float8"),
)

# Lista de valores de uma coluna: CHECK ((status)::text = ANY ((ARRAY['a'::…])::text[]))
# (também "col IS NULL OR col IN (…)"); POSITION('@' IN email) e afins não entram.
ALLOWED_VALUES = re.compile(r"= ANY \(\(ARRAY\[")

FONT = "DejaVu Sans Mono, Menlo, Consolas, monospace"
CHAR_W = 7.3
ROW_H = 18
HEADER_H = 26
COL_GAP = 70
TABLE_GAP = 28
MARGIN = 40
COLUMNS = 5


def _short_type(text):
    for long, short in TYPE_ABBREVIATIONS:
        text = text.replace(long, short)
    return text


def load_schema():
    tables = {}
    for model in apps.get_models():
        if model._meta.app_label in SAM_APPS and not model._meta.managed:
            tables[model._meta.db_table] = {
                "module": model._meta.app_label,
                "view": model._meta.db_table.startswith("vw_"),
            }

    columns = defaultdict(list)
    pks, fks, checks, enums = defaultdict(set), defaultdict(set), {}, defaultdict(list)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attidentity, a.attgenerated "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'v') "
            "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY c.relname, a.attnum"
        )
        for table, column, type_, not_null, identity, generated in cursor.fetchall():
            if table in tables:
                columns[table].append(
                    {
                        "name": column,
                        "type": _short_type(type_),
                        "not_null": not_null,
                        "identity": bool(identity),
                        "generated": bool(generated),
                    }
                )
        cursor.execute(
            "SELECT con.conrelid::regclass::text, a.attname, con.contype, con.confrelid::regclass::text, "
            "pg_get_constraintdef(con.oid), cardinality(con.conkey) "
            "FROM pg_constraint con "
            "JOIN LATERAL unnest(con.conkey) AS k(attnum) ON true "
            "JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum "
            "WHERE con.connamespace = 'public'::regnamespace AND con.contype IN ('p', 'f', 'c') "
            "ORDER BY 1, 2, 3"
        )
        for table, column, kind, parent, definition, width in cursor.fetchall():
            if kind == "p":
                pks[table].add(column)
            elif kind == "f":
                fks[(table, column)].add(
                    parent
                )  # uma coluna pode estar em mais de uma FK
            elif kind == "c" and width == 1 and ALLOWED_VALUES.search(definition):
                # Só a lista de valores de UMA coluna (status IN (...)); regras com
                # várias colunas ou funções (POSITION('@' IN email)) ficam de fora.
                checks[(table, column)] = re.findall(r"'([^']*)'::", definition)
        cursor.execute(
            "SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
            "WHERE t.typnamespace = 'public'::regnamespace ORDER BY t.typname, e.enumsortorder"
        )
        for type_name, label in cursor.fetchall():
            enums[type_name].append(label)
    return tables, columns, pks, fks, checks, enums


def _wrap(prefix, values, width_chars):
    lines, current = [], prefix
    for value in values:
        piece = value if current == prefix else f", {value}"
        if len(current) + len(piece) > width_chars and current != prefix:
            lines.append(current + ",")
            current = "  " + value
        else:
            current += piece
    lines.append(current)
    return lines


def render(schema):
    tables, columns, pks, fks, checks, enums = schema
    boxes = {}
    for table in sorted(tables):
        rows = []
        for col in columns[table]:
            mark = "PK" if col["name"] in pks[table] else ""
            refs = sorted(fks.get((table, col["name"]), ()))
            flags = []
            if col["not_null"] and not mark:
                flags.append("NN")
            if col["generated"]:
                flags.append("gerada")
            right = f"→ {', '.join(refs)}" if refs else ""
            text = f"{col['name']}: {col['type']}" + (
                f" ({', '.join(flags)})" if flags else ""
            )
            rows.append(
                {
                    "text": text,
                    "mark": mark,
                    "right": right,
                    "column": col["name"],
                    "allowed": False,
                }
            )
            values = checks.get((table, col["name"]))
            if values is None and col["type"] in enums:
                values = enums[col["type"]]
            if values:
                for line in _wrap("∈ ", values, 44):
                    rows.append(
                        {
                            "text": line,
                            "mark": "",
                            "right": "",
                            "column": None,
                            "allowed": True,
                        }
                    )
        longest = max(
            [len(table) + 8] + [len(r["text"]) + len(r["right"]) + 6 for r in rows]
        )
        width = max(300, round(longest * CHAR_W) + 24)
        boxes[table] = {
            "rows": rows,
            "width": width,
            "height": HEADER_H + ROW_H * len(rows) + 8,
            **tables[table],
        }

    # Módulos em colunas (preenchendo a mais baixa), na ordem do domínio.
    col_width = max(b["width"] for b in boxes.values())
    heights = [MARGIN + 70] * COLUMNS
    placed = {}
    module_labels = []
    for module in SAM_APPS:
        names = sorted(
            (t for t in boxes if boxes[t]["module"] == module),
            key=lambda t: (boxes[t]["view"], t),
        )
        if not names:
            continue
        index = heights.index(min(heights))
        x = MARGIN + index * (col_width + COL_GAP)
        y = heights[index]
        module_labels.append((module, x, y))
        y += 26
        for name in names:
            placed[name] = (x, y)
            y += boxes[name]["height"] + TABLE_GAP
        heights[index] = y + 20

    enum_y = max(heights) + 10
    enum_lines = []
    for type_name in sorted(enums):
        enum_lines.extend(_wrap(f"{type_name} ∈ ", enums[type_name], 150))
    total_w = MARGIN * 2 + COLUMNS * col_width + (COLUMNS - 1) * COL_GAP
    total_h = enum_y + 40 + ROW_H * len(enum_lines) + MARGIN

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
        f'viewBox="0 0 {total_w} {total_h}" font-family="{FONT}" font-size="12">',
        "<!-- GERADO por `python manage.py schema_diagram` a partir do banco migrado "
        "(database/init.sql + migrations). Não edite à mão. -->",
        '<defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8a94a6"/></marker></defs>',
        f'<rect width="{total_w}" height="{total_h}" fill="#ffffff"/>',
        f'<text x="{MARGIN}" y="{MARGIN + 6}" font-size="22" font-weight="bold" fill="#1f2933">'
        "SAM — modelo físico do banco (PostgreSQL)</text>",
        f'<text x="{MARGIN}" y="{MARGIN + 30}" fill="#52606d">PK chave primária · NN obrigatório · '
        "→ chave estrangeira · ∈ valores permitidos (CHECK/ENUM) · views em tracejado · "
        "gerado de database/init.sql + migrations</text>",
    ]

    # Ligações (atrás das caixas).
    out.append(
        '<g fill="none" stroke="#8a94a6" stroke-opacity="0.55" stroke-width="1.2">'
    )
    for table in sorted(boxes):
        for i, row in enumerate(boxes[table]["rows"]):
            for parent in (
                sorted(fks.get((table, row["column"]), ())) if row["column"] else ()
            ):
                if parent in placed:
                    out.append(_edge(boxes, placed, table, i, parent))
    out.append("</g>")

    for module, x, y in module_labels:
        out.append(
            f'<text x="{x}" y="{y + 14}" font-size="14" font-weight="bold" fill="{COLORS[module]}">'
            f"{escape(MODULE_TITLES[module])} ({module})</text>"
        )

    for table in sorted(boxes):
        box = boxes[table]
        x, y = placed[table]
        color = COLORS[box["module"]]
        dash = ' stroke-dasharray="6 4"' if box["view"] else ""
        out.append(f'<g id="{escape(table)}">')
        out.append(
            f'<rect x="{x}" y="{y}" width="{box["width"]}" height="{box["height"]}" rx="6" fill="#ffffff" stroke="{color}" stroke-width="1.5"{dash}/>'
        )
        out.append(
            f'<path d="M {x} {y + 6} a 6 6 0 0 1 6 -6 h {box["width"] - 12} a 6 6 0 0 1 6 6 v {HEADER_H - 6} h {-box["width"]} z" fill="{color}"/>'
        )
        label = f"{table.upper()}{'  (view)' if box['view'] else ''}"
        out.append(
            f'<text x="{x + 10}" y="{y + 17}" font-weight="bold" fill="#ffffff">{escape(label)}</text>'
        )
        for i, row in enumerate(box["rows"]):
            ry = y + HEADER_H + ROW_H * i + 15
            if row["allowed"]:
                out.append(
                    f'<text x="{x + 34}" y="{ry}" fill="#7b8794" font-style="italic">{escape(row["text"])}</text>'
                )
                continue
            if row["mark"]:
                out.append(
                    f'<text x="{x + 8}" y="{ry}" font-weight="bold" fill="{color}">{row["mark"]}</text>'
                )
            out.append(
                f'<text x="{x + 34}" y="{ry}" fill="#1f2933">{escape(row["text"])}</text>'
            )
            if row["right"]:
                out.append(
                    f'<text x="{x + box["width"] - 8}" y="{ry}" text-anchor="end" fill="#52606d">{escape(row["right"])}</text>'
                )
        out.append("</g>")

    out.append(
        f'<text x="{MARGIN}" y="{enum_y + 14}" font-size="14" font-weight="bold" fill="#1f2933">Tipos ENUM</text>'
    )
    for i, line in enumerate(enum_lines):
        out.append(
            f'<text x="{MARGIN}" y="{enum_y + 36 + ROW_H * i}" fill="#1f2933">{escape(line)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _edge(boxes, placed, table, row_index, parent):
    """Curva da linha da coluna (lado mais próximo) até o cabeçalho da tabela referenciada."""
    x, y = placed[table]
    row_y = y + HEADER_H + ROW_H * row_index + ROW_H / 2 + 4
    px, py = placed[parent]
    if px > x:
        sx, ex = x + boxes[table]["width"], px
    elif px < x:
        sx, ex = x, px + boxes[parent]["width"]
    else:
        sx, ex = x + boxes[table]["width"], px + boxes[parent]["width"]
    ey = py + HEADER_H / 2
    if px == x:
        c1, c2 = sx + 40, ex + 40
    else:
        bend = 60 if px > x else -60
        c1, c2 = sx + bend, ex - bend
    return (
        f'<path d="M {sx:.0f} {row_y:.0f} C {c1:.0f} {row_y:.0f}, {c2:.0f} {ey:.0f}, '
        f'{ex:.0f} {ey:.0f}" marker-end="url(#seta)"/>'
    )


def default_output():
    return Path(settings.BASE_DIR).parent / "docs" / "DIAGRAMA_SAM.svg"


class Command(BaseCommand):
    help = "Gera o diagrama físico do banco (docs/DIAGRAMA_SAM.svg) a partir do schema migrado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=None,
            help="Arquivo SVG (padrão: docs/DIAGRAMA_SAM.svg).",
        )

    def handle(self, *args, **options):
        output = Path(options["output"]) if options["output"] else default_output()
        output.write_text(render(load_schema()), encoding="utf-8")
        self.stdout.write(f"Diagrama gravado em {output}")
