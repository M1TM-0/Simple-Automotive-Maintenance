import re

from django.core.exceptions import ValidationError

PLATE_PATTERN = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
# 12 primeiros caracteres alfanuméricos + 2 dígitos verificadores numéricos (CNPJ alfanumérico, RFB 2026)
CNPJ_PATTERN = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
_ASCII_SPACES = re.compile(r"\s+", re.ASCII)

_CNPJ_WEIGHTS_FIRST = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_WEIGHTS_SECOND = (6, *_CNPJ_WEIGHTS_FIRST)


def _cnpj_digit(chars, weights):
    # Valor de cada caractere = código ASCII - 48 ("0"-"9" -> 0-9, "A"-"Z" -> 17-42).
    # Para CNPJs só numéricos o resultado é idêntico ao cálculo tradicional.
    remainder = (
        sum((ord(c) - 48) * w for c, w in zip(chars, weights, strict=False)) % 11
    )
    return "0" if remainder < 2 else str(11 - remainder)


def cnpj_check_digits(base):
    first = _cnpj_digit(base, _CNPJ_WEIGHTS_FIRST)
    second = _cnpj_digit(base + first, _CNPJ_WEIGHTS_SECOND)
    return first + second


def normalize_cnpj(value):
    """Remove pontuação (. / -) e espaços e coloca em maiúsculas, preservando as letras."""
    return re.sub(r"[\s./-]", "", value or "").upper()


def is_valid_cnpj(value):
    if not (value or "").isascii():
        return False

    cnpj = normalize_cnpj(value)

    if not CNPJ_PATTERN.fullmatch(cnpj) or len(set(cnpj)) == 1:
        return False

    return cnpj[12:] == cnpj_check_digits(cnpj[:12])


def validate_cnpj(value):
    """Valida o CNPJ (numérico ou alfanumérico) e devolve os 14 caracteres normalizados."""
    if not is_valid_cnpj(value):
        raise ValidationError("CNPJ inválido.", code="invalid_cnpj")
    return normalize_cnpj(value)


def normalize_plate(value):
    return re.sub(r"[\s-]", "", value or "").upper()


def validate_plate(value):
    """Valida placa antiga (AAA9999) ou Mercosul (AAA9A99) e devolve a forma normalizada."""
    plate = normalize_plate(value)
    if not PLATE_PATTERN.match(plate):
        raise ValidationError("Placa inválida.", code="invalid_plate")
    return plate


def clean_service_name(value):
    """Equivalente a clean_service_name() do banco: colapsa espaços e apara as pontas."""
    return _ASCII_SPACES.sub(" ", value).strip(" ")


def normalize_service_name(value):
    """Equivalente a normalize_service_name() do banco: chave de unicidade."""
    return clean_service_name(value).lower()
