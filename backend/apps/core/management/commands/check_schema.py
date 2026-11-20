"""Confere o banco contra o `init.sql` e as migrations (BE-091, seção 13.3 do backlog).

    python manage.py check_schema [--json]

Lê os nomes de tabelas, views, tipos, funções, triggers e índices declarados no
`init.sql` (SAM_INIT_SQL_PATH, o mesmo arquivo que a migration core/0001 aplica) e
confere que cada um existe no banco; confere também que não há migration pendente e que
o catálogo semeado está presente. Sai com erro se algo faltar: o `deploy/deploy.sh`
chama este comando depois do `migrate`, antes de trocar a versão no ar.
"""

import json
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor

DECLARATIONS = {
    "tables": re.compile(
        r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.I | re.M
    ),
    "views": re.compile(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)", re.I | re.M),
    "types": re.compile(r"^\s*CREATE\s+TYPE\s+(\w+)", re.I | re.M),
    "functions": re.compile(
        r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)", re.I | re.M
    ),
    "triggers": re.compile(r"^\s*CREATE\s+TRIGGER\s+(\w+)", re.I | re.M),
    "indexes": re.compile(
        r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
        re.I | re.M,
    ),
}

EXISTING = {
    "tables": "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
    "views": "SELECT viewname FROM pg_views WHERE schemaname = 'public'",
    "types": (
        "SELECT t.typname FROM pg_type t WHERE t.typnamespace = 'public'::regnamespace "
        "AND t.typtype IN ('e', 'c', 'd') AND NOT EXISTS "
        "(SELECT 1 FROM pg_class c WHERE c.reltype = t.oid)"
    ),
    "functions": "SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace",
    "triggers": (
        "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace"
    ),
    "indexes": "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'",
}

# Catálogo semeado pelo init.sql (pode crescer: o admin aprova serviços novos).
SEEDS = {
    "service": ("SELECT count(*) FROM service", 62),
    "service_category": ("SELECT count(*) FROM service_category", 11),
}


def declared_objects(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"--[^\n]*", "", text)  # comentários de linha
    return {
        kind: sorted({name.lower() for name in rx.findall(text)})
        for kind, rx in DECLARATIONS.items()
    }


def inspect(connection, init_sql_path):
    declared = declared_objects(init_sql_path)
    report = {"objects": {}, "missing": {}, "seeds": {}, "pending_migrations": []}
    with connection.cursor() as cursor:
        for kind, sql in EXISTING.items():
            cursor.execute(sql)
            existing = {row[0].lower() for row in cursor.fetchall()}
            missing = [name for name in declared[kind] if name not in existing]
            report["objects"][kind] = {
                "init_sql": len(declared[kind]),
                "database": len(existing),
            }
            if missing:
                report["missing"][kind] = missing
        for table, (sql, minimum) in SEEDS.items():
            cursor.execute(sql)
            found = cursor.fetchone()[0]
            report["seeds"][table] = found
            if found < minimum:
                report["missing"].setdefault("seeds", []).append(
                    f"{table}: {found} < {minimum}"
                )

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    report["pending_migrations"] = [f"{m.app_label}.{m.name}" for m, _ in plan]
    report["ok"] = not report["missing"] and not report["pending_migrations"]
    return report


class Command(BaseCommand):
    help = "Confere o banco contra o init.sql (tabelas, views, triggers, funções…) e as migrations."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Saída em JSON.")
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS)

    def handle(self, *args, **options):
        path = settings.SAM_INIT_SQL_PATH
        if not path.is_file():
            raise CommandError(
                f"init.sql não encontrado em {path} (SAM_INIT_SQL_PATH)."
            )
        report = inspect(connections[options["database"]], path)

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            for kind, numbers in report["objects"].items():
                self.stdout.write(
                    f"{kind}: {numbers['init_sql']} do init.sql, {numbers['database']} no banco"
                )
            for table, found in report["seeds"].items():
                self.stdout.write(f"{table}: {found} linhas")

        if not report["ok"]:
            problems = dict(report["missing"])
            if report["pending_migrations"]:
                problems["migrations"] = report["pending_migrations"]
            raise CommandError(
                f"Schema divergente: {json.dumps(problems, ensure_ascii=False)}"
            )
        if not options["json"]:
            self.stdout.write(
                self.style.SUCCESS("Schema confere com o init.sql e as migrations.")
            )
