"""BE-086 — Nenhuma consulta monta SQL por concatenação (SQL Injection, A03).

Varre o código Python do backend e falha se encontrar:

* `QuerySet.raw(...)`, `QuerySet.extra(...)` ou `RawSQL(...)`;
* `cursor.execute(...)`/`executemany(...)` cujo SQL seja f-string, `%`, `+` ou
  `.format(...)`. Valores vão sempre como parâmetros (`execute(sql, [valores])`).

Exceção consciente (ex.: nomes de tabela vindos dos modelos, nunca do usuário):
comentário `# sql-safe: <motivo>` em uma das linhas da chamada. O ruff também roda a regra
`S608` (flake8-bandit) no CI.
"""

import ast
from pathlib import Path

from django.conf import settings

BACKEND = Path(settings.BASE_DIR)
SCANNED = ["apps", "config", "tests", "conftest.py"]
FORBIDDEN_CALLS = {"raw", "extra"}
EXECUTE = {"execute", "executemany"}
MARKER = "# sql-safe:"


def _python_files():
    for entry in SCANNED:
        path = BACKEND / entry
        if path.is_file():
            yield path
        else:
            yield from (
                p
                for p in path.rglob("*.py")
                if "migrations" not in p.parts or p.name != "__init__.py"
            )


def _is_interpolated(node):
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def _offenses(path):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else getattr(node.func, "id", None)
        )
        span = lines[
            node.lineno - 1 : node.end_lineno
        ]  # a chamada pode ocupar várias linhas
        if any(MARKER in line for line in span):
            continue
        if name == "RawSQL" or (
            name in FORBIDDEN_CALLS
            and isinstance(node.func, ast.Attribute)
            and _queryset_like(node)
        ):
            yield f"{path.relative_to(BACKEND)}:{node.lineno}: {name}()"
        if name in EXECUTE and node.args and _is_interpolated(node.args[0]):
            yield f"{path.relative_to(BACKEND)}:{node.lineno}: SQL interpolado em {name}()"


def _queryset_like(node):
    """`.raw()`/`.extra()` de QuerySet/Manager (não `dict.extra`, `logger.extra` etc.)."""
    target = node.func.value
    text = ast.unparse(target)
    return "objects" in text or "queryset" in text.lower() or text.endswith("_set")


def test_no_raw_sql_built_by_interpolation():
    offenses = [offense for path in _python_files() for offense in _offenses(path)]
    assert not offenses, "SQL montado por interpolação ou raw()/extra():\n" + "\n".join(
        offenses
    )


def test_the_scanner_catches_the_forbidden_shapes(tmp_path):
    sample = tmp_path / "amostra.py"
    sample.write_text(
        "def f(cursor, q, Client):\n"
        "    cursor.execute(f\"SELECT * FROM client WHERE name = '{q}'\")\n"
        "    cursor.execute('SELECT %s' % q)\n"
        "    cursor.execute('SELECT ' + q)\n"
        "    cursor.execute('SELECT {}'.format(q))\n"
        "    Client.objects.raw('SELECT 1')\n"
        "    Client.objects.extra(where=['1=1'])\n"
        "    cursor.execute('SELECT %s', [q])\n"
        "    cursor.execute('TRUNCATE ' + q)  # sql-safe: teste\n",
        encoding="utf-8",
    )
    global BACKEND
    original, BACKEND = BACKEND, tmp_path
    try:
        found = list(_offenses(sample))
    finally:
        BACKEND = original
    assert len(found) == 6, found
