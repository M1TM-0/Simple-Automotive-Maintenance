"""Busca por texto normalizado (DP-19, BE-036).

Regra documentada e determinística, igual no Python e no SQL: espaços colapsados,
pontas aparadas, minúsculas e **sem acentos/cedilha** do português — `?q=oleo`
encontra "Troca de óleo" e `?q=ÓLEO` também. Não usa a extensão `unaccent`
(o `init.sql` não a instala): a remoção de acentos é feita com `translate()`.
Esta normalização é só para BUSCA; a unicidade de nomes de serviço continua sendo
`normalize_service_name()` do banco (que preserva acentos).
"""

import re
import unicodedata

from apps.core.limits import SEARCH, clean_query_text
from django.db.models import CharField, F, Func, Q, Value
from django.db.models.functions import Lower

# Maiúsculas acentuadas também entram: `lower()` do banco depende do locale
# (LC_CTYPE); com o mapa completo o resultado não depende dele.
ACCENTED = "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ"
PLAIN = "aaaaaeeeeiiiiooooouuuucn" * 2
_SPACES = re.compile(r"\s+")
MAX_QUERY_LENGTH = SEARCH


def normalize_search_text(value) -> str:
    text = _SPACES.sub(" ", str(value or "")).strip().lower()[:MAX_QUERY_LENGTH]
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


class _Translate(Func):
    function = "translate"
    output_field = CharField()


class _CollapseSpaces(Func):
    template = "regexp_replace(%(expressions)s, '\\s+', ' ', 'g')"
    output_field = CharField()


def normalized(field_name):
    """Expressão SQL equivalente a `normalize_search_text` aplicada a uma coluna."""
    return Lower(
        _Translate(_CollapseSpaces(F(field_name)), Value(ACCENTED), Value(PLAIN))
    )


def search_filter(queryset, query, *fields):
    """Filtra `queryset` pelos registros cujo algum campo contém o termo normalizado.

    `query` vem da query string (`?q=`): NUL ou mais de 100 caracteres → 400 em `q`
    (BE-086). O termo vai ao banco só como parâmetro (`LIKE` do ORM), nunca no SQL.
    """
    term = normalize_search_text(clean_query_text(query))
    if not term:
        return queryset
    annotations = {f"_search_{i}": normalized(name) for i, name in enumerate(fields)}
    condition = Q()
    for alias in annotations:
        condition |= Q(**{f"{alias}__contains": term})
    return queryset.alias(**annotations).filter(condition)
