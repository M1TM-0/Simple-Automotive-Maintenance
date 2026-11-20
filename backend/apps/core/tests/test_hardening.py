"""Testes das correções da revisão da Fase 1.

Cobrem: CNPJ alfanumérico, números gigantes em dinheiro, mascaramento de campos
`extra` nos logs e JPEG no formato MPO.
"""

import io
import json
import logging

import pytest
from apps.core import money, validators
from apps.core.images import InvalidImageError, process_image
from apps.core.logging import JsonFormatter, RequestContextFilter, SensitiveDataFilter
from apps.core.tests.factories import WorkshopFactory
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from PIL import Image

# ---------------------------------------------------------------- CNPJ alfanumérico


def alnum_cnpj(base):
    return base + validators.cnpj_check_digits(base)


def test_cnpj_check_digits_match_the_official_alphanumeric_example():
    # Exemplo da documentação da Receita Federal: 12.ABC.345/01DE-35
    assert validators.cnpj_check_digits("12ABC34501DE") == "35"


@pytest.mark.parametrize(
    "value",
    ["12ABC34501DE35", "12.ABC.345/01DE-35", "12abc34501de35", " 12.ABC.345/01DE-35 "],
)
def test_alphanumeric_cnpj_is_valid_and_normalized(value):
    assert validators.validate_cnpj(value) == "12ABC34501DE35"


@pytest.mark.parametrize(
    "value",
    [
        "12ABC34501DE34",  # dígito verificador errado
        "12ABC34501DEXX",  # verificadores precisam ser numéricos
        "12ABC34501DE3",  # curto
        "12ABC34501DE355",  # longo
        "AAAAAAAAAAAAAA",  # todos iguais
        "12ABC345ß1DE35",  # não ASCII
    ],
)
def test_alphanumeric_cnpj_invalid(value):
    with pytest.raises(ValidationError):
        validators.validate_cnpj(value)


@pytest.mark.django_db
def test_database_accepts_alphanumeric_cnpj():
    workshop = WorkshopFactory(cnpj=alnum_cnpj("12ABC34501DE"))
    workshop.refresh_from_db()

    assert workshop.cnpj == "12ABC34501DE35"


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["12abc34501de35", "12ABC34501DEXX", "12ABC34501DE3"])
def test_database_still_rejects_malformed_cnpj(bad):
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkshopFactory(cnpj=bad)


# ---------------------------------------------------------------- dinheiro: entradas gigantes


@pytest.mark.parametrize("value", ["1" * 40, "1e1000", "9" * 30 + ".5", "-" + "1" * 40])
@pytest.mark.parametrize(
    "function",
    [
        money.validate_unit_price,
        money.validate_quantity,
        money.to_money,
        money.to_quantity,
    ],
)
def test_huge_numbers_raise_validation_error_not_decimal_error(function, value):
    with pytest.raises(ValidationError):
        function(value)


def test_subtotal_rejects_huge_numbers_with_validation_error():
    with pytest.raises(ValidationError):
        money.subtotal("1" * 40, "1.00")


def test_subtotal_at_the_limits_is_exact_and_rounds_half_up():
    # 9999999.999 x 99999999.99 = 999999999800000.00001 -> 2 casas, half-up
    assert money.subtotal("9999999.999", "99999999.99") == money.to_money(
        "999999999800000.00"
    )
    assert money.subtotal("2.5", "0.01") == money.to_money(
        "0.03"
    )  # 0.025 -> 0.03 (half-up)


# ---------------------------------------------------------------- logs: campos extra


def emit(**extra):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    handler.addFilter(SensitiveDataFilter())
    logger = logging.getLogger("sam.hardening.test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.warning("evento", extra=extra)
    return json.loads(stream.getvalue())


def test_sensitive_extra_keys_are_masked():
    payload = emit(
        password="SENHA", token="TOKEN", authorization="Bearer abc", sessionid="SID"
    )

    assert payload["password"] == payload["token"] == "***"
    assert payload["authorization"] == payload["sessionid"] == "***"
    assert "SENHA" not in json.dumps(payload)


def test_secrets_inside_extra_text_and_nested_values_are_masked():
    payload = emit(
        detail="falhou com password=abc123", nested={"new_password": "x", "ok": "y"}
    )

    assert "abc123" not in payload["detail"]
    assert payload["nested"] == {"new_password": "***", "ok": "y"}


def test_harmless_extra_fields_are_kept():
    payload = emit(budgets_expired=3, role="client")

    assert payload["budgets_expired"] == 3
    assert payload["role"] == "client"


# ---------------------------------------------------------------- imagens MPO


def mpo_bytes():
    first = Image.new("RGB", (120, 90), "red")
    second = Image.new("RGB", (120, 90), "blue")
    buffer = io.BytesIO()
    first.save(buffer, format="MPO", save_all=True, append_images=[second])
    return buffer.getvalue()


def test_mpo_photo_is_accepted_and_reencoded_as_plain_jpeg():
    assert (
        Image.open(io.BytesIO(mpo_bytes())).format == "MPO"
    )  # pré-condição do cenário

    processed = process_image(io.BytesIO(mpo_bytes()))

    assert processed.content_type == "image/jpeg"
    assert processed.extension == "jpg"
    assert Image.open(io.BytesIO(processed.content)).format == "JPEG"


def test_non_image_is_still_rejected():
    with pytest.raises(InvalidImageError):
        process_image(io.BytesIO(b"isto nao e uma imagem"))
