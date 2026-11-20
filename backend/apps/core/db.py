from datetime import timedelta

from django.db import models
from django.db.models import Func


class CurrentTimestamp(Func):
    """CURRENT_TIMESTAMP do PostgreSQL (início da transação), igual ao DEFAULT do schema."""

    template = "CURRENT_TIMESTAMP"
    output_field = models.DateTimeField()


class ClockTimestamp(Func):
    """clock_timestamp() do PostgreSQL: o instante real da instrução (não o início da transação).

    Usado onde a ordem de gravação importa para leituras incrementais (ex.: `date_sent`
    do chat, BE-058): com CURRENT_TIMESTAMP uma transação longa gravaria um horário
    anterior a mensagens já confirmadas por outras transações.
    """

    template = "clock_timestamp()"
    output_field = models.DateTimeField()


def timestamp_plus_days(days):
    return CurrentTimestamp() + timedelta(days=days)
