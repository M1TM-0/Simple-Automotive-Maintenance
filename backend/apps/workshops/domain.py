from apps.core.timeutils import business_now, to_business_time


def is_setup_complete(workshop) -> bool:
    """Cadastro oficial concluído (BE-028, DP-06): a oficina tem ao menos 1 serviço.

    Conta qualquer linha de WORKSHOP_SERVICE — do catálogo global ou personalizada
    (inclusive `pending`, que aguarda análise) —, exceto solicitação `rejected`,
    que não é um serviço da oficina. Ponto no mapa e horários são opcionais.
    """
    from apps.catalog.models import SolicitationStatus, WorkshopService

    return (
        WorkshopService.objects.filter(workshop_id=workshop.pk)
        .exclude(status_solicitation=SolicitationStatus.REJECTED)
        .exists()
    )


def business_clock(moment=None) -> tuple[int, object]:
    """(dia ISO 1–7, hora) no fuso do negócio (DP-16) — a régua de OPERATION_HOUR.

    Perfil público e mapa usam esta mesma função, então `is_open_now` e o filtro
    `open_now` nunca discordam (e os testes controlam o relógio por aqui).
    """
    moment = to_business_time(moment) if moment is not None else business_now()
    return moment.isoweekday(), moment.time().replace(tzinfo=None)


def is_open_at(hours, moment=None) -> bool | None:
    """Aberto agora pelos horários da oficina: `abertura <= hora < fechamento`.

    Sem nenhum horário cadastrado o estado é desconhecido → `None` (a interface
    mostra "Não informado"), não `False`.
    """
    hours = list(hours)
    if not hours:
        return None
    day, now = business_clock(moment)
    return any(
        h.day_of_week == day and h.opening_time <= now < h.closing_time for h in hours
    )
