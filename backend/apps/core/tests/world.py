"""Mundo de teste com dois lados simétricos, A e B (BE-084, BE-081, BE-083).

Cada lado tem um cliente, uma oficina com cadastro concluído e tudo o que as rotas
da seção 8 alcançam: veículo com histórico (manual e gerado pela entrega),
atendimento entregue com avaliação, atendimento aguardando aprovação com orçamento
e item, chat com mensagens, notificações dos dois perfis, favorito, promoção com
divulgação, denúncia, produto e solicitação de serviço personalizado. O cliente de
um lado **nunca** interage com a oficina do outro.

Os campos privados de cada lado levam o marcador `SEGREDO-<lado>` (e-mail, nome do
responsável, observações, notas técnicas, mensagens, notificações, descrição da
denúncia e conteúdos que não podem ser públicos: produto e promoção inativos,
avaliação oculta). A suíte de autorização procura o marcador de B em toda resposta
dada a A — e nas respostas públicas sobre B.

Use `build_world()` dentro de um teste ou numa fixture com acesso ao banco.
"""

import itertools
from dataclasses import dataclass

from apps.attendances.models import AttendanceStatus
from apps.catalog.models import SolicitationStatus
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    ChatFactory,
    ClientFactory,
    DenunciationFactory,
    FavoriteFactory,
    MessageFactory,
    NotificationFactory,
    OperationHourFactory,
    PagWorkshopFactory,
    PointOfInterestFactory,
    ProductFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
    RegisterMaintenanceFactory,
    ServiceCategoryFactory,
    VehicleFactory,
    WorkshopServiceFactory,
    deliver_attendance,
    make_review,
)

SECRET = "SEGREDO"


def marker(label: str) -> str:
    return f"{SECRET}-{label}"


@dataclass
class Side:
    """Os objetos de um lado do mundo (A ou B)."""

    label: str
    marker: str
    client: object
    workshop: object
    vehicle: object
    history_record: object  # registro manual (REGISTER_MAINTENANCE)
    delivered_attendance: object
    delivered_budget: object
    review: object  # publicada
    hidden_review: object  # oculta: nunca aparece em leitura pública
    attendance: object  # aguardando aprovação (waiting_approval)
    budget: object  # orçamento pendente já enviado
    budget_item: object
    workshop_service: object  # serviço do catálogo
    service_request: object  # serviço personalizado pendente
    product: object  # ativo
    inactive_product: object
    promotion: object  # ativa e vigente
    inactive_promotion: object
    advertisement: object
    chat: object
    notification_client: object
    notification_workshop: object
    favorite: object
    denunciation: object

    def entity(self, name: str, role: str | None = None):
        """Valor do parâmetro de caminho que aponta para o recurso `name` deste lado."""
        notification = (
            self.notification_workshop
            if role == "workshop"
            else self.notification_client
        )
        values = {
            "attendance": self.attendance.pk,
            "budget": self.budget.pk,
            "budget_item": self.budget_item.pk,
            "client": self.client.pk,
            "vehicle": self.vehicle.pk,
            "chat": self.chat.pk,
            "workshop": self.workshop.pk,
            "promotion": self.promotion.pk,
            "product": self.product.pk,
            "workshop_service": self.workshop_service.pk,
            "history_record": f"service-{self.history_record.pk}",
            "notification": notification.pk,
            "review": self.review.pk,
            "denunciation": self.denunciation.pk,
            "service_request": self.service_request.pk,
        }
        return values[name]


@dataclass
class World:
    a: Side
    b: Side

    def side(self, label: str) -> Side:
        return {"A": self.a, "B": self.b}[label]


def _move(attendance, status):
    attendance.status_attendance = status
    attendance.save(update_fields=["status_attendance"])


def build_side(label: str) -> Side:
    secret = marker(label)
    lower = secret.lower()

    client = ClientFactory(
        name=f"Cliente {label}", email=f"cliente.{lower}@exemplo.com"
    )
    point = PointOfInterestFactory(name=f"Oficina {label}")
    page = PagWorkshopFactory(
        workshop__name_fantasy=f"Oficina {label}",
        workshop__name_responsible=f"Responsável {secret}",
        workshop__email=f"oficina.{lower}@exemplo.com",
        workshop__point_of_interest=point,
    )
    workshop = page.workshop
    workshop_service = WorkshopServiceFactory(workshop=workshop)
    OperationHourFactory(
        workshop=workshop, day_of_week=1, opening_time="08:00", closing_time="18:00"
    )

    vehicle = VehicleFactory(
        client=client, information=f"Informação {secret}", history_shared=True
    )
    history_record = RegisterMaintenanceFactory(
        vehicle=vehicle, observations=f"Histórico {secret}"
    )

    delivered = AttendanceFactory(
        client=client,
        workshop=workshop,
        vehicle=vehicle,
        observations=f"Pedido {secret}",
        technical_notes=f"Notas {secret}",
    )
    delivered_budget, *_ = deliver_attendance(delivered)
    review = make_review(
        delivered_budget, comment=f"Ótimo atendimento da oficina {label}"
    )

    hidden = AttendanceFactory(client=client, workshop=workshop, vehicle=vehicle)
    hidden_budget, *_ = deliver_attendance(hidden)
    hidden_review = make_review(
        hidden_budget, comment=f"Oculta {secret}", status_review="hidden"
    )

    attendance = AttendanceFactory(
        client=client,
        workshop=workshop,
        vehicle=vehicle,
        observations=f"Pedido {secret}",
        technical_notes=f"Notas {secret}",
    )
    budget = BudgetFactory(attendance=attendance, observations=f"Orçamento {secret}")
    budget_item = BudgetItemFactory(budget=budget, description="Mão de obra")
    _move(attendance, AttendanceStatus.WAITING_APPROVAL)
    attendance.refresh_from_db()
    budget.refresh_from_db()

    service_request = WorkshopServiceFactory(
        workshop=workshop,
        service=None,
        name_local=f"Serviço personalizado {label}",
        suggested_category=ServiceCategoryFactory(),
        status_solicitation=SolicitationStatus.PENDING,
    )
    product = ProductFactory(workshop=workshop, name=f"Produto {label}")
    inactive_product = ProductFactory(
        workshop=workshop, description=f"Inativo {secret}", active=False
    )

    promotion = PromotionFactory(
        workshop=workshop, title=f"Promoção {label}", workshop_service=workshop_service
    )
    inactive_promotion = PromotionFactory(
        workshop=workshop,
        title="Encerrada",
        description=f"Inativa {secret}",
        workshop_service=workshop_service,
        status_promotion="inactive",
    )
    advertisement = PromotionAdvertisementFactory(promotion=promotion)

    chat = ChatFactory(client=client, workshop=workshop)
    MessageFactory(chat=chat, content=f"Mensagem do cliente {secret}")
    MessageFactory(
        chat=chat,
        sender_client=None,
        sender_workshop=workshop,
        content=f"Resposta {secret}",
    )

    notification_client = NotificationFactory(client=client, message=f"Aviso {secret}")
    notification_workshop = NotificationFactory(
        client=None, workshop=workshop, message=f"Aviso {secret}"
    )
    favorite = FavoriteFactory(client=client, workshop=workshop)
    denunciation = DenunciationFactory(
        client=client,
        promotion=promotion,
        reason="other",
        description=f"Denúncia {secret}",
    )

    return Side(
        label=label,
        marker=secret,
        client=client,
        workshop=workshop,
        vehicle=vehicle,
        history_record=history_record,
        delivered_attendance=delivered,
        delivered_budget=delivered_budget,
        review=review,
        hidden_review=hidden_review,
        attendance=attendance,
        budget=budget,
        budget_item=budget_item,
        workshop_service=workshop_service,
        service_request=service_request,
        product=product,
        inactive_product=inactive_product,
        promotion=promotion,
        inactive_promotion=inactive_promotion,
        advertisement=advertisement,
        chat=chat,
        notification_client=notification_client,
        notification_workshop=notification_workshop,
        favorite=favorite,
        denunciation=denunciation,
    )


def build_world() -> World:
    return World(a=build_side("A"), b=build_side("B"))


def truncate_sam_tables():
    """Apaga os dados de todas as tabelas do domínio (as do catálogo semeado ficam)."""
    from django.apps import apps
    from django.db import connection

    seeded = {"service", "service_category"}
    tables = sorted(
        model._meta.db_table
        for model in apps.get_models()
        if not model._meta.managed
        and model._meta.db_table not in seeded
        and not model._meta.db_table.startswith("vw_")
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"
        )  # sql-safe: nomes vêm dos modelos
        # Serviços e categorias criados pelas fábricas (o seed do init.sql tem ids baixos e fica).
        cursor.execute("DELETE FROM service WHERE name LIKE %s", ["Serviço de teste %"])
        cursor.execute(
            "DELETE FROM service_category WHERE name LIKE %s", ["Categoria de teste %"]
        )


_GROWTH = itertools.count()


def grow_side(side: Side, n: int = 3) -> None:
    """Multiplica por `n` tudo o que as listagens e detalhes do lado alcançam (BE-083).

    Usado para provar que o número de consultas de cada rota não cresce com o volume
    (sem N+1): mede, chama `grow_side`, mede de novo.
    """
    from apps.core.tests.factories import ClientFactory, NotificationFactory

    client, workshop, vehicle = side.client, side.workshop, side.vehicle
    for _ in range(n):
        i = next(_GROWTH)  # nomes e horários únicos entre chamadas
        # Veículos do cliente com histórico (manual e de entrega) e mais histórico no veículo principal.
        extra_vehicle = VehicleFactory(client=client, history_shared=True)
        RegisterMaintenanceFactory(vehicle=extra_vehicle, observations="Extra")
        RegisterMaintenanceFactory(
            vehicle=vehicle,
            service_name=f"Rodízio {i}",
            interval_km=10000,
            mileage_km=40000 + i,
        )
        delivered = AttendanceFactory(
            client=client, workshop=workshop, vehicle=extra_vehicle
        )
        budget, *_ = deliver_attendance(delivered)
        make_review(budget, comment=f"Avaliação {i}")
        deliver_attendance(
            AttendanceFactory(client=client, workshop=workshop, vehicle=vehicle)
        )

        # Atendimentos aguardando aprovação, com orçamento e itens.
        waiting = AttendanceFactory(
            client=client, workshop=workshop, vehicle=extra_vehicle
        )
        pending = BudgetFactory(attendance=waiting)
        BudgetItemFactory(budget=pending)
        _move(waiting, AttendanceStatus.WAITING_APPROVAL)

        # Outras oficinas públicas: chat, favorito e denúncia do cliente.
        other = PagWorkshopFactory().workshop
        other_service = WorkshopServiceFactory(workshop=other)
        other_chat = ChatFactory(client=client, workshop=other)
        MessageFactory(chat=other_chat, content=f"Oi {i}")
        MessageFactory(
            chat=other_chat,
            sender_client=None,
            sender_workshop=other,
            content=f"Olá {i}",
        )
        FavoriteFactory(client=client, workshop=other)
        other_promotion = PromotionFactory(
            workshop=other, workshop_service=other_service
        )
        DenunciationFactory(client=client, promotion=other_promotion, reason="spam")

        # Outros clientes atendidos pela oficina, com conversa.
        new_client = ClientFactory()
        new_vehicle = VehicleFactory(client=new_client, history_shared=True)
        AttendanceFactory(client=new_client, workshop=workshop, vehicle=new_vehicle)
        chat = ChatFactory(client=new_client, workshop=workshop)
        MessageFactory(chat=chat, content=f"Pergunta {i}")

        # Mensagens no chat principal, notificações, catálogo e vitrine da oficina.
        MessageFactory(chat=side.chat, content=f"Mais uma {i}")
        NotificationFactory(client=client, message=f"Aviso {i}")
        NotificationFactory(client=None, workshop=workshop, message=f"Aviso {i}")
        ProductFactory(workshop=workshop, name=f"Produto extra {i}")
        promotion = PromotionFactory(
            workshop=workshop,
            workshop_service=side.workshop_service,
            title=f"Oferta {i}",
        )
        PromotionAdvertisementFactory(promotion=promotion)
        PromotionAdvertisementFactory(promotion=side.promotion)
        WorkshopServiceFactory(workshop=workshop)
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local=f"Personalizado {side.label} {i}",
            suggested_category=ServiceCategoryFactory(),
            status_solicitation=SolicitationStatus.PENDING,
        )
        PointOfInterestFactory(name=f"Borracharia {i}", type="borracharia")
        OperationHourFactory(
            workshop=workshop,
            day_of_week=2 + i % 6,
            opening_time=f"{i // 6 % 24:02d}:00",
            closing_time=f"{i // 6 % 24:02d}:30",
        )
