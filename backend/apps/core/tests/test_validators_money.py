from decimal import Decimal

import pytest
from apps.core import money, validators
from django.core.exceptions import ValidationError
from django.db import connection


@pytest.mark.parametrize(
    "value", ["11.222.333/0001-81", "11222333000181", " 11.222.333/0001-81 "]
)
def test_cnpj_valid(value):
    assert validators.validate_cnpj(value) == "11222333000181"


@pytest.mark.parametrize(
    "value", ["11111111111111", "11222333000182", "123", "", "abcdefghijklmn"]
)
def test_cnpj_invalid(value):
    with pytest.raises(ValidationError):
        validators.validate_cnpj(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("abc-1d23", "ABC1D23"), (" abc 1234 ", "ABC1234"), ("ABC1D23", "ABC1D23")],
)
def test_plate_normalization(raw, expected):
    assert validators.validate_plate(raw) == expected


@pytest.mark.parametrize("raw", ["AB1234", "ABCD123", "1234567", ""])
def test_plate_invalid(raw):
    with pytest.raises(ValidationError):
        validators.validate_plate(raw)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name",
    [
        "  Troca   de óleo ",
        "Troca\tde\nÓleo",
        "Alinhamento e balanceamento",
        "A  B   C",
    ],
)
def test_service_name_matches_database_functions(name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT clean_service_name(%s), normalize_service_name(%s)", [name, name]
        )
        db_clean, db_normalized = cursor.fetchone()

    assert validators.clean_service_name(name) == db_clean
    assert validators.normalize_service_name(name) == db_normalized


def test_money_never_uses_float():
    assert money.money_str(Decimal("0.1") + Decimal("0.2")) == "0.30"
    with pytest.raises(ValidationError):
        money.to_decimal(0.1)


def test_money_rounding_matches_half_up():
    assert money.to_money("2.675") == Decimal("2.68")
    assert money.subtotal("3", "33.335") == Decimal("100.01")


@pytest.mark.parametrize("value", ["0", "-1", "0.0005", "1.2345"])
def test_quantity_rejected(value):
    with pytest.raises(ValidationError):
        money.validate_quantity(value)


def test_quantity_and_price_accepted():
    assert money.validate_quantity("1.250") == Decimal("1.250")
    assert money.validate_unit_price("10") == Decimal("10.00")
    with pytest.raises(ValidationError):
        money.validate_unit_price("-0.01")
    with pytest.raises(ValidationError):
        money.validate_unit_price("1.005")
