"""Eventos de negócio → notificações (BE-070, RF-S03). Textos em pt-BR.

Cada função monta título, mensagem e destino (`url` de página do frontend) e chama
`notify()`, que só grava depois do commit. São chamadas pelos serviços dentro da
transação do caso de uso (ver README, seção 6).

| Evento | Destinatário | Título | Destino |
|---|---|---|---|
| Novo atendimento (`request_attendance`) | oficina | Nova solicitação de atendimento | `w-attendance.html?id=A` |
| Cliente cancelou (`cancel_attendance`) | oficina | Atendimento cancelado pelo cliente | `w-attendance.html?id=A` |
| Orçamento aprovado/recusado (`respond_budget`) | oficina | Orçamento aprovado / recusado | `w-attendance.html?id=A` |
| Nova avaliação (`create_review`) | oficina | Nova avaliação recebida | `w-reviews.html` |
| Serviço personalizado aprovado/rejeitado (BE-074) | oficina | Serviço aprovado / não aprovado | `w-services.html` |
| Promoção/divulgação retirada por denúncia procedente (BE-073) | oficina | Conteúdo retirado pela moderação | `w-promotions.html` |
| Pagamento da divulgação confirmado / divulgação no ar (BE-076) | oficina | Pagamento confirmado / Divulgação no ar | `w-promotions.html` |
| Divulgação paga cancelada → estorno (BE-076) | oficina | Estorno da divulgação | `w-promotions.html` |
| Orçamento enviado (`send_budget`) | cliente | Orçamento recebido | `attendance.html?id=A` |
| Mudança de status pela oficina (`transition_attendance`) | cliente | Serviço iniciado / reaberto / concluído / Veículo entregue / Atendimento cancelado pela oficina | `attendance.html?id=A` |
| Orçamento expirado (rotina de expiração) | cliente | Orçamento expirado | `attendance.html?id=A` |
| Resposta à avaliação (`respond_review`) | cliente | A oficina respondeu à sua avaliação | `attendance.html?id=A` |
| Denúncia resolvida (BE-073) | cliente denunciante | Denúncia procedente / Denúncia analisada | — (sem link) |
| Manutenção preventiva perto do prazo / vencida (BE-077, rotina `send_maintenance_reminders`) | cliente | Manutenção próxima / Manutenção vencida (1 por ciclo) | `vehicle.html?id=V` |
| Nova mensagem (`send_message`) | interlocutor | Nova mensagem de X / N novas mensagens de X (1 por conversa até ler) | `chat.html?id=C` |

Sem e-mail (DP-11): o canal é só o sino/T08.
"""

from apps.attendances.models import AttendanceStatus
from apps.core.timeutils import to_business_time
from apps.notifications.services import notify, notify_chat_message
from apps.reviews.domain import author_display_name

PREVIEW_MAX = 140


def brl(value) -> str:
    """`Decimal('1234.5')` → `R$ 1.234,50`."""
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def _date_time(moment) -> str:
    return to_business_time(moment).strftime("%d/%m/%Y às %H:%M")


def _vehicle(vehicle) -> str:
    return f"{vehicle.brand} {vehicle.model} ({vehicle.plate})"


def km(value: int) -> str:
    """`49500` → `49.500 km`."""
    return f"{value:,}".replace(",", ".") + " km"


def _client_url(attendance_id) -> str:
    return f"attendance.html?id={attendance_id}"


def _workshop_url(attendance_id) -> str:
    return f"w-attendance.html?id={attendance_id}"


def preview(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= PREVIEW_MAX else text[: PREVIEW_MAX - 1].rstrip() + "…"


# ------------------------------------------------------------- para a oficina


def attendance_requested(attendance) -> None:
    client = author_display_name(attendance.client.name) or "Um cliente"
    notify(
        "workshop",
        attendance.workshop_id,
        "Nova solicitação de atendimento",
        f"{client} solicitou atendimento para {_vehicle(attendance.vehicle)}.",
        _workshop_url(attendance.pk),
    )


def attendance_canceled_by_client(attendance) -> None:
    client = author_display_name(attendance.client.name) or "O cliente"
    notify(
        "workshop",
        attendance.workshop_id,
        "Atendimento cancelado pelo cliente",
        f"{client} cancelou o atendimento #{attendance.pk} ({_vehicle(attendance.vehicle)}).",
        _workshop_url(attendance.pk),
    )


def budget_responded(budget, *, approved: bool) -> None:
    attendance = budget.attendance
    client = author_display_name(attendance.client.name) or "O cliente"
    if approved:
        title = "Orçamento aprovado"
        message = (
            f"{client} aprovou o orçamento de {brl(budget.total_price)} do atendimento "
            f"#{attendance.pk}. Você já pode iniciar o serviço."
        )
    else:
        title = "Orçamento recusado"
        message = (
            f"{client} recusou o orçamento do atendimento #{attendance.pk}. "
            "Você pode enviar uma nova proposta."
        )
    notify("workshop", budget.workshop_id, title, message, _workshop_url(attendance.pk))


def review_created(review) -> None:
    attendance = review.budget.attendance
    client = author_display_name(attendance.client.name) or "Um cliente"
    stars = "estrela" if review.rating == 1 else "estrelas"
    notify(
        "workshop",
        review.budget.workshop_id,
        "Nova avaliação recebida",
        f"{client} avaliou o atendimento #{attendance.pk} com {review.rating} {stars}.",
        "w-reviews.html",
    )


def service_request_decided(workshop_service, *, approved: bool) -> None:
    """Para a moderação (BE-074): solicitação de serviço personalizado decidida."""
    name = workshop_service.name_local or "personalizado"
    if approved:
        title = "Serviço aprovado"
        message = f"O serviço “{name}” foi aprovado e entrou no catálogo do SAM."
    else:
        title = "Serviço não aprovado"
        reason = workshop_service.motivation_rejection
        message = f"O serviço “{name}” não foi aprovado." + (
            f" Motivo: {reason}" if reason else ""
        )
    notify("workshop", workshop_service.workshop_id, title, message, "w-services.html")


PROMOTIONS_URL = "w-promotions.html"


def content_removed_by_moderation(
    workshop_id: int, *, promotion_title: str, advertisement: bool
) -> None:
    """BE-073: denúncia procedente contra promoção (desativada) ou divulgação (cancelada)."""
    what = (
        f"A divulgação da promoção “{promotion_title}” foi cancelada"
        if advertisement
        else f"A promoção “{promotion_title}” foi desativada"
    )
    notify(
        "workshop",
        workshop_id,
        "Conteúdo retirado pela moderação",
        f"{what} após a análise de uma denúncia.",
        PROMOTIONS_URL,
    )


def advertisement_paid(advertisement, *, live: bool) -> None:
    """BE-076: pagamento confirmado pelo admin (DP-09); se o período já começou, já está no ar."""
    title = advertisement.promotion.title
    if live:
        notify(
            "workshop",
            advertisement.promotion.workshop_id,
            "Divulgação no ar",
            f"Pagamento confirmado: a divulgação da promoção “{title}” já está no ar "
            f"até {_date_time(advertisement.date_end)}.",
            PROMOTIONS_URL,
        )
        return
    notify(
        "workshop",
        advertisement.promotion.workshop_id,
        "Pagamento confirmado",
        f"Recebemos o pagamento de {brl(advertisement.advertising_price)} da divulgação da promoção "
        f"“{title}”. Ela entra no ar em {_date_time(advertisement.date_start)}.",
        PROMOTIONS_URL,
    )


def advertisement_live(advertisement) -> None:
    """BE-076: a rotina colocou no ar uma divulgação paga cujo período começou."""
    notify(
        "workshop",
        advertisement.promotion.workshop_id,
        "Divulgação no ar",
        f"A divulgação da promoção “{advertisement.promotion.title}” está no ar "
        f"até {_date_time(advertisement.date_end)}.",
        PROMOTIONS_URL,
    )


def advertisement_refunded(advertisement) -> None:
    """BE-076: divulgação paga cancelada (promoção desativada, moderação ou admin)."""
    notify(
        "workshop",
        advertisement.promotion.workshop_id,
        "Estorno da divulgação",
        f"A divulgação da promoção “{advertisement.promotion.title}” foi cancelada. "
        f"O valor de {brl(advertisement.advertising_price)} será estornado.",
        PROMOTIONS_URL,
    )


# --------------------------------------------------------------- para o cliente


def budget_sent(budget) -> None:
    attendance = budget.attendance
    notify(
        "client",
        attendance.client_id,
        "Orçamento recebido",
        f"{attendance.workshop.name_fantasy} enviou um orçamento de {brl(budget.total_price)} "
        f"para {_vehicle(attendance.vehicle)}. Responda até {_date_time(budget.date_validity)}.",
        _client_url(attendance.pk),
    )


_STATUS_MESSAGES = {
    AttendanceStatus.IN_PROGRESS: (
        "Serviço iniciado",
        "{workshop} iniciou o serviço em {vehicle}.",
    ),
    AttendanceStatus.COMPLETED: (
        "Serviço concluído",
        "{workshop} concluiu o serviço em {vehicle}. Combine a retirada do veículo.",
    ),
    AttendanceStatus.DELIVERED: (
        "Veículo entregue",
        "{workshop} registrou a entrega de {vehicle}. Conte como foi: avalie o atendimento.",
    ),
    AttendanceStatus.CANCELED: (
        "Atendimento cancelado pela oficina",
        "{workshop} cancelou o atendimento #{id} ({vehicle}).",
    ),
}
_REOPENED = (
    "Serviço reaberto",
    "{workshop} reabriu o serviço em {vehicle} para ajustes.",
)


def attendance_status_changed(attendance, previous_status: str) -> None:
    """Transição feita pela oficina (BE-050)."""
    status = attendance.status_attendance
    if (
        status == AttendanceStatus.IN_PROGRESS
        and previous_status == AttendanceStatus.COMPLETED
    ):
        title, template = _REOPENED
    elif status in _STATUS_MESSAGES:
        title, template = _STATUS_MESSAGES[status]
    else:
        return
    message = template.format(
        workshop=attendance.workshop.name_fantasy,
        vehicle=_vehicle(attendance.vehicle),
        id=attendance.pk,
    )
    notify("client", attendance.client_id, title, message, _client_url(attendance.pk))


def budget_expired(budget) -> None:
    attendance = budget.attendance
    notify(
        "client",
        attendance.client_id,
        "Orçamento expirado",
        f"O orçamento de {attendance.workshop.name_fantasy} para {_vehicle(attendance.vehicle)} "
        "venceu sem resposta. Peça um novo orçamento à oficina, se ainda quiser o serviço.",
        _client_url(attendance.pk),
    )


def review_responded(review) -> None:
    attendance = review.budget.attendance
    notify(
        "client",
        attendance.client_id,
        "A oficina respondeu à sua avaliação",
        f"{attendance.workshop.name_fantasy}: “{preview(review.workshop_response)}”",
        _client_url(attendance.pk),
    )


def _denounced_content(denunciation) -> str:
    if denunciation.review_id:
        return f"uma avaliação de {denunciation.review.budget.workshop.name_fantasy}"
    if denunciation.promotion_id:
        promotion = denunciation.promotion
        return f"a promoção “{promotion.title}” de {promotion.workshop.name_fantasy}"
    promotion = denunciation.advertisement.promotion
    return f"a divulgação da promoção “{promotion.title}” de {promotion.workshop.name_fantasy}"


def denunciation_resolved(denunciation) -> None:
    """BE-073: o denunciante sabe o resultado; o texto interno da decisão não é enviado."""
    content = _denounced_content(denunciation)
    if denunciation.status_denunciation == "upheld":
        title = "Denúncia procedente"
        message = (
            f"Analisamos sua denúncia sobre {content} e ela foi considerada procedente. "
            "O conteúdo foi retirado do ar. Obrigado por ajudar."
        )
    else:
        title = "Denúncia analisada"
        message = (
            f"Analisamos sua denúncia sobre {content} e não encontramos violação das regras. "
            "O conteúdo foi mantido."
        )
    notify("client", denunciation.client_id, title, message)


# ---------------------------------------------------------------------- ambos


def message_sent(message, chat, sender_role: str) -> None:
    """Uma notificação não lida por conversa (agrupada em `notify_chat_message`)."""
    if sender_role == "client":
        recipient_role, recipient_id = "workshop", chat.workshop_id
        sender_name = author_display_name(chat.client.name) or "Cliente"
    else:
        recipient_role, recipient_id = "client", chat.client_id
        sender_name = chat.workshop.name_fantasy
    notify_chat_message(
        chat.pk, recipient_role, recipient_id, sender_name, preview(message.content)
    )


def maintenance_due(vehicle, item) -> None:
    """BE-077: um aviso por ciclo do item (a rotina garante que não repete)."""
    what = f"{item.service_name} do {_vehicle(vehicle)}"
    if item.remaining_km > 0:
        title = "Manutenção próxima"
        message = f"{what}: faltam {km(item.remaining_km)} (prevista aos {km(item.next_mileage_km)})."
    else:
        title = "Manutenção vencida"
        late = (
            f"passou {km(-item.remaining_km)} da quilometragem prevista ({km(item.next_mileage_km)})"
            if item.remaining_km < 0
            else f"chegou à quilometragem prevista ({km(item.next_mileage_km)})"
        )
        message = f"{what}: {late}."
    notify(
        "client",
        vehicle.client_id,
        title,
        message + " Encontre uma oficina pelo mapa do SAM.",
        f"vehicle.html?id={vehicle.pk}",
    )
