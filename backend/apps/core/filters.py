from django_filters import BaseInFilter, CharFilter, ChoiceFilter


class CommaSeparatedFilter(BaseInFilter, CharFilter):
    """Aceita listas separadas por vírgula: ?status=requested,budgeted."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lookup_expr", "in")
        super().__init__(*args, **kwargs)


class CommaSeparatedChoiceFilter(BaseInFilter, ChoiceFilter):
    """Lista separada por vírgula com cada valor validado contra `choices` (400 se inválido).

    Necessário para colunas ENUM do PostgreSQL (ex.: `status_attendance`): um valor
    fora do tipo viraria erro de SQL em vez de erro de validação.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lookup_expr", "in")
        super().__init__(*args, **kwargs)
