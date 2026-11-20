from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")

MAX_UNIT_PRICE = Decimal("99999999.99")
MAX_QUANTITY = Decimal("9999999.999")

# Maior expoente aceito (|valor| < 10**16). Evita estourar a precisão do Decimal
# (decimal.InvalidOperation) em quantize() com entradas absurdas como "1e1000".
MAX_ADJUSTED_EXPONENT = 15


def to_decimal(value):
    """Converte para Decimal sem aceitar float (imprecisão binária)."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool) or isinstance(value, float):
        raise ValidationError(
            "Informe o valor como texto ou inteiro, nunca como float."
        )
    elif isinstance(value, int | str):
        try:
            result = Decimal(str(value).strip().replace(",", "."))
        except InvalidOperation:
            raise ValidationError("Valor numérico inválido.") from None
    else:
        raise ValidationError("Valor numérico inválido.")

    if not result.is_finite():
        raise ValidationError("Valor numérico inválido.")
    if result.adjusted() > MAX_ADJUSTED_EXPONENT:
        raise ValidationError("Valor numérico fora do limite permitido.")
    return result


def to_money(value):
    return to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def to_quantity(value):
    return to_decimal(value).quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def _check_places(value, places, label):
    if value != value.quantize(places):
        raise ValidationError(
            f"{label} aceita no máximo {abs(places.as_tuple().exponent)} casas decimais."
        )


def validate_unit_price(value):
    price = to_decimal(value)
    if price < 0:
        raise ValidationError("O preço unitário não pode ser negativo.")
    _check_places(price, MONEY_PLACES, "O preço unitário")
    if price > MAX_UNIT_PRICE:
        raise ValidationError("O preço unitário excede o limite permitido.")
    return price.quantize(MONEY_PLACES)


def validate_quantity(value):
    quantity = to_decimal(value)
    if quantity <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")
    _check_places(quantity, QUANTITY_PLACES, "A quantidade")
    if quantity > MAX_QUANTITY:
        raise ValidationError("A quantidade excede o limite permitido.")
    return quantity.quantize(QUANTITY_PLACES)


def subtotal(quantity, unit_price):
    """Mesma regra da coluna gerada BUDGET_ITEM.subtotal: ROUND(quantidade × preço, 2)."""
    with localcontext() as context:
        context.prec = 60
        return (to_decimal(quantity) * to_decimal(unit_price)).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )


def money_str(value):
    return format(to_money(value), "f")
