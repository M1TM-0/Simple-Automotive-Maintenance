"""Validação de respostas reais contra o schema OpenAPI gerado (BE-081).

`ContractClient` embrulha um `APIClient`: cada resposta é casada com a operação do
schema (método + caminho), o status precisa estar documentado e o corpo JSON é
validado contra o schema daquele status em modo **estrito**:

* campos `required` presentes, tipos, `enum`, `pattern` (decimais) e formatos de data;
* `nullable` respeitado (OpenAPI 3.0 → JSON Schema `anyOf [..., null]`);
* objeto com `properties` não aceita campo fora do schema (o frontend lê o que o schema
  promete; campo não documentado é contrato implícito).

Respostas 2xx validadas ficam registradas em `COVERAGE` para provar que toda operação
foi exercitada.
"""

import copy
import json
import re
import uuid
from datetime import date, datetime, time
from functools import cache

from drf_spectacular.generators import SchemaGenerator
from jsonschema import Draft202012Validator, FormatChecker

METHODS = ("get", "post", "put", "patch", "delete")


@cache
def openapi():
    return SchemaGenerator().get_schema(request=None, public=True)


def _convert(node):
    """OpenAPI 3.0 → JSON Schema 2020-12 (nullable, $ref e objetos estritos)."""
    if isinstance(node, list):
        return [_convert(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _convert(value) for key, value in node.items()}
    if "$ref" in node:
        node["$ref"] = node["$ref"].replace("#/components/schemas/", "#/$defs/")
    if (
        node.get("type") == "object"
        and "properties" in node
        and "additionalProperties" not in node
    ):
        node["additionalProperties"] = False
    for key in (
        "readOnly",
        "writeOnly",
        "example",
        "discriminator",
        "externalDocs",
        "xml",
    ):
        node.pop(key, None)
    if node.pop("nullable", False):
        if "enum" in node and None not in node["enum"]:
            node["enum"] = [*node["enum"], None]
        node = {"anyOf": [node, {"type": "null"}]}
    return node


@cache
def _definitions():
    return _convert(copy.deepcopy(openapi()["components"]["schemas"]))


def _check_datetime(value):
    if not isinstance(value, str):
        return True
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return True


def _check_date(value):
    if not isinstance(value, str):
        return True
    date.fromisoformat(value)
    return True


def _check_time(value):
    """Hora ISO 8601 (`08:00` ou `08:00:00`): é o que a API devolve e a tela T17 usa."""
    if not isinstance(value, str):
        return True
    time.fromisoformat(value)
    return True


def _check_uuid(value):
    if not isinstance(value, str):
        return True
    uuid.UUID(value)
    return True


FORMATS = FormatChecker()
FORMATS.checks("date-time", raises=ValueError)(_check_datetime)
FORMATS.checks("date", raises=ValueError)(_check_date)
FORMATS.checks("uuid", raises=ValueError)(_check_uuid)
FORMATS.checks("time", raises=ValueError)(_check_time)


@cache
def _routes():
    compiled = []
    for path, item in openapi()["paths"].items():
        pattern = re.compile("^" + re.sub(r"\{[^}]+\}", r"[^/]+", path) + "$")
        for method, operation in item.items():
            if method in METHODS:
                compiled.append((method.upper(), path, pattern, operation))
    return compiled


def find_operation(method, url_path):
    for op_method, path, pattern, operation in _routes():
        if op_method == method and pattern.match(url_path):
            return path, operation
    return None, None


def all_operations():
    return {(method, path) for method, path, _, _ in _routes()}


class ContractViolation(AssertionError):
    pass


COVERAGE: set = set()
VIOLATIONS: list = []


def validate_response(method, url, response):
    """Valida a resposta e devolve a chave `(método, caminho do schema)`."""
    url_path = url.split("?", 1)[0]
    path, operation = find_operation(method, url_path)
    if operation is None:
        raise ContractViolation(f"{method} {url_path}: rota fora do schema")

    responses = operation["responses"]
    status = str(response.status_code)
    if status not in responses and "default" not in responses:
        raise ContractViolation(
            f"{method} {path}: status {status} não documentado ({sorted(responses)})"
        )

    spec = responses.get(status) or responses["default"]
    content = spec.get("content", {})
    body = response.content
    if response.status_code == 204 or not content:
        if body:
            raise ContractViolation(
                f"{method} {path}: {status} documentado sem corpo, veio {body[:80]!r}"
            )
    else:
        media = content.get("application/json")
        if media is None:
            raise ContractViolation(
                f"{method} {path}: {status} sem application/json no schema"
            )
        if not response["Content-Type"].startswith("application/json"):
            raise ContractViolation(
                f"{method} {path}: Content-Type {response['Content-Type']}"
            )
        schema = {**_convert(copy.deepcopy(media["schema"])), "$defs": _definitions()}
        errors = sorted(
            Draft202012Validator(schema, format_checker=FORMATS).iter_errors(
                json.loads(body)
            ),
            key=lambda e: list(e.absolute_path),
        )
        if errors:
            detail = "; ".join(
                f"{'/'.join(map(str, e.absolute_path)) or '<raiz>'}: {e.message[:200]}"
                for e in errors[:5]
            )
            raise ContractViolation(f"{method} {path} [{status}]: {detail}")

    if 200 <= response.status_code < 300:
        COVERAGE.add((method, path))
    return method, path


class ContractClient:
    """`APIClient` que valida toda resposta contra o schema e guarda o último corpo por URL."""

    def __init__(self, api):
        self.api = api
        self.recorded = {}

    def _call(self, method, url, data=None, fmt="json", expect=None):
        if method == "GET":
            response = self.api.get(url, data or {})
            if data:
                from urllib.parse import urlencode

                url = f"{url}?{urlencode(data)}"
        elif fmt == "multipart":
            response = getattr(self.api, method.lower())(
                url, data or {}, format="multipart"
            )
        else:
            response = self.api.generic(
                method,
                url,
                json.dumps(data) if data is not None else "",
                content_type="application/json",
            )
        if expect is not None:
            assert response.status_code == expect, (
                f"{method} {url}: {response.status_code} {response.content[:300]!r}"
            )
        try:
            validate_response(method, url, response)
        except ContractViolation as violation:
            VIOLATIONS.append(str(violation))
        self.recorded[f"{method} {url}"] = {
            "status": response.status_code,
            "body": json.loads(response.content) if response.content else None,
        }
        return response

    def get(self, url, params=None, expect=200):
        return self._call("GET", url, params, expect=expect)

    def post(self, url, data=None, expect=201, fmt="json"):
        return self._call("POST", url, data, fmt, expect)

    def patch(self, url, data=None, expect=200, fmt="json"):
        return self._call("PATCH", url, data, fmt, expect)

    def put(self, url, data=None, expect=200):
        return self._call("PUT", url, data, "json", expect)

    def delete(self, url, expect=204):
        return self._call("DELETE", url, None, "json", expect)
