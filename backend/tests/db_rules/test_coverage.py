"""BE-079 — toda trigger (16) e toda função de regra do banco têm ≥ 1 teste positivo e
≥ 1 negativo nesta suíte (registro feito por `@covers` em `support.py`).

Trigger ou função nova no schema sem teste → este teste falha com o nome dela.
"""

import importlib
import pkgutil

import pytest

import tests.db_rules
from tests.db_rules.support import COVERAGE

pytestmark = [pytest.mark.db_rules, pytest.mark.django_db]


def _load_all_rule_modules():
    for module in pkgutil.iter_modules(tests.db_rules.__path__):
        if module.name.startswith("test_"):
            importlib.import_module(f"tests.db_rules.{module.name}")


def _rows(sql):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return [row[0] for row in cursor.fetchall()]


def test_every_trigger_and_rule_function_is_proved_both_ways():
    _load_all_rule_modules()
    triggers = _rows(
        "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace"
    )
    # Funções que não são de trigger (as de trigger são provadas pelos triggers acima).
    functions = _rows(
        "SELECT p.proname FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace "
        "AND p.prorettype <> 'trigger'::regtype"
    )
    assert len(triggers) == 16
    assert len(functions) == 11

    missing = []
    for name in sorted(set(triggers) | set(functions)):
        entry = COVERAGE.get(name, {"positive": set(), "negative": set()})
        for kind in ("positive", "negative"):
            if not entry[kind]:
                missing.append(f"{name} ({kind})")
    assert not missing, "sem teste: " + ", ".join(missing)
