"""BE-082 — Fluxos ponta a ponta F1–F8 no navegador (frontend real → API → banco).

Cada teste dirige as telas como um usuário: preenche formulários, clica e confere o
que aparece na tela **e** o que ficou gravado no banco (as regras são das triggers).
"""

import io
import re
from datetime import timedelta

import pytest
from apps.accounts.models import Favorite, Workshop
from apps.attendances.models import Attendance
from apps.catalog.models import WorkshopService
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    ClientFactory,
    PointOfInterestFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
    VehicleFactory,
    deliver_attendance,
    make_ready_workshop,
    make_review,
)
from apps.reviews.models import Denunciation, Review
from apps.vehicles.models import RegisterMaintenance, Vehicle
from django.utils import timezone
from PIL import Image

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def _jpeg(tmp_path, name="carro.jpg"):
    path = tmp_path / name
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (200, 40, 40)).save(buffer, format="JPEG")
    path.write_bytes(buffer.getvalue())
    return str(path)


def _workshop_near(name="Auto Center Teste"):
    """Oficina pública (cadastro concluído) com ponto no mapa e horário."""
    workshop = make_ready_workshop()
    point = PointOfInterestFactory(
        name=name, latitude="-5.091200", longitude="-42.803100", address="Rua A, 1"
    )
    Workshop.objects.filter(pk=workshop.pk).update(
        name_fantasy=name, point_of_interest=point
    )
    workshop.refresh_from_db()
    return workshop


# ---------------------------------------------------------------- F1


def test_f1_client_signup_vehicle_with_photos_history_and_login(sessions, tmp_path):
    client = sessions("cliente")
    page = client.go("register.html")
    page.fill("#name", "Ana Souza")
    page.fill("#email", "ana@exemplo.com")
    page.fill("#pw", "SenhaForte123")
    page.fill("#pw2", "SenhaForte123")
    page.click("#sb")
    page.wait_for_url("**/vehicles.html")

    page = client.go("vehicle-new.html")
    page.fill("#brand", "Fiat")
    page.fill("#model", "Argo")
    page.fill("#year_fabrication", "2020")
    page.fill("#year_model", "2021")
    page.fill("#mileage_km", "41000")
    page.fill("#plate", "QWE1R23")
    page.select_option("#fuel", "flex")
    page.select_option("#exchange", "manual")
    page.set_input_files("#ph", [_jpeg(tmp_path, "a.jpg"), _jpeg(tmp_path, "b.jpg")])
    page.wait_for_function("document.querySelectorAll('#pv img').length === 2")
    page.click("#sv")
    page.wait_for_url(re.compile(r"vehicle\.html\?id=\d+"))

    vehicle = Vehicle.objects.get(client__email="ana@exemplo.com")
    assert vehicle.plate == "QWE1R23"
    assert vehicle.photo_1 and vehicle.photo_2 and not vehicle.photo_3

    # Histórico manual (só inclusão) com intervalo para a próxima troca.
    page.fill("#hs", "Troca de óleo")
    page.fill("#hk", "41000")
    page.fill("#hi", "10000")
    page.fill("#hn", "Óleo 5W30")
    page.click("#hb")
    page.locator("#tl").get_by_text("Troca de óleo").first.wait_for()
    assert RegisterMaintenance.objects.filter(
        vehicle=vehicle, service_name="Troca de óleo", interval_km=10000
    ).exists()

    # Placa repetida no mesmo cliente: a tela mostra o erro da API no campo.
    page = client.go("vehicle-new.html")
    for field, value in {
        "#brand": "Fiat",
        "#model": "Uno",
        "#year_fabrication": "2015",
        "#year_model": "2016",
        "#mileage_km": "90000",
        "#plate": "QWE1R23",
    }.items():
        page.fill(field, value)
    page.select_option("#fuel", "flex")
    page.select_option("#exchange", "manual")
    page.click("#sv")
    page.locator("#e-plate").get_by_text(
        "Já existe um veículo com esta placa."
    ).wait_for()
    assert Vehicle.objects.filter(client__email="ana@exemplo.com").count() == 1

    # Novo navegador: login leva à garagem com o veículo.
    again = sessions("cliente-login")
    page = again.login(vehicle.client, password="SenhaForte123")
    page.wait_for_url("**/vehicles.html")
    page.get_by_text("Argo").first.wait_for()


# ---------------------------------------------------------------- F2


def test_f2_workshop_signup_and_setup_wizard(sessions):
    PointOfInterestFactory(name="Auto Center Rocha", address="Av. Frei Serafim, 100")
    workshop = sessions("oficina")
    page = workshop.go("register.html")
    page.locator("label", has=page.locator("input[name=role][value=workshop]")).click()
    page.fill("#name_fantasy", "Auto Center Rocha")
    page.fill("#name_responsible", "Carlos Rocha")
    page.fill("#cnpj", "11222333000181")
    page.fill("#email", "rocha@exemplo.com")
    page.fill("#pw", "SenhaForte123")
    page.fill("#pw2", "SenhaForte123")
    page.click("#sb")
    page.wait_for_url("**/workshop-setup.html")

    # 1. Dados
    page.fill("#phone_number", "86999990000")
    page.click("#b1")
    # 2. Ponto no mapa: busca, confirma que é seu e vincula
    page.fill("[data-q]", "Rocha")
    page.click("[data-go]")
    page.locator("[data-pick]").first.click()
    page.check("[data-ok]")
    page.click("[data-link]")
    page.get_by_text("Ponto vinculado:").wait_for()
    page.click("[data-next]")
    # 3. Horários: segunda 08–12 e 13–18
    page.click('[data-add="1"]')
    page.fill('[data-d="1"][data-i="0"][data-k=o]', "08:00")
    page.fill('[data-d="1"][data-i="0"][data-k=c]', "12:00")
    page.click('[data-add="1"]')
    page.fill('[data-d="1"][data-i="1"][data-k=o]', "13:00")
    page.fill('[data-d="1"][data-i="1"][data-k=c]', "18:00")
    page.click("[data-next]")
    # 4. Serviços do catálogo
    first = page.locator("input[data-s]").first
    first.check()
    service_id = first.get_attribute("data-s")
    page.fill(f'[data-p="{service_id}"]', "120,00")
    page.fill(f'#cw [data-d="{service_id}"]', "60")
    page.click("[data-next]")
    page.wait_for_url("**/w-attendances.html")

    account = Workshop.objects.get(email="rocha@exemplo.com")
    assert account.point_of_interest.name == "Auto Center Rocha"
    assert account.operation_hours.count() == 2
    assert WorkshopService.objects.filter(
        workshop=account, service_id=int(service_id)
    ).exists()


# ---------------------------------------------------------------- F3


def test_f3_map_profile_favorite_and_request(sessions):
    workshop = _workshop_near()
    customer = ClientFactory(name="Bruno Lima")
    VehicleFactory(client=customer, brand="Honda", model="Civic")

    client = sessions("cliente")
    client.login(customer)
    page = client.go("map.html")
    page.locator("#list a.shopc", has_text="Auto Center Teste").click()
    page.wait_for_url(f"**/shop.html?id={workshop.pk}")

    page.click("#bf")
    page.wait_for_selector('#bf[aria-pressed="true"]')
    assert Favorite.objects.filter(client=customer, workshop=workshop).exists()

    page.click("#br")
    page.select_option("#id_vehicle", index=1)
    page.fill("#observations", "Barulho na suspensão dianteira")
    page.get_by_role("button", name="Enviar solicitação").click()
    page.get_by_text("Solicitação enviada.").wait_for()
    attendance = Attendance.objects.get(client=customer, workshop=workshop)
    assert (attendance.status_attendance, attendance.observations) == (
        "requested",
        "Barulho na suspensão dianteira",
    )


# ---------------------------------------------------------------- F4


def test_f4_budget_approval_execution_delivery_history_review_and_response(sessions):
    workshop = _workshop_near()
    service = WorkshopService.objects.get(workshop=workshop)
    customer = ClientFactory(name="Carla Dias")
    vehicle = VehicleFactory(client=customer, brand="VW", model="Gol")
    attendance = AttendanceFactory(
        client=customer,
        workshop=workshop,
        vehicle=vehicle,
        observations="Revisão geral",
    )

    # Oficina: cria o orçamento, inclui o serviço do catálogo e envia.
    shop = sessions("oficina")
    shop.login(workshop, "workshop")
    page = shop.go(f"w-budget.html?attendance={attendance.pk}")
    page.click("#mk")
    page.click("#add")
    row = page.locator("#rows tr").first
    row.locator("[data-f=type]").select_option("service")
    row.locator("[data-f=origin]").select_option(f"s{service.pk}")
    row.locator("[data-rst]").get_by_text("Salvo").wait_for()
    page.wait_for_selector("#send:not([disabled])")
    page.click("#send")
    page.click("#cfs [data-yes]")
    page.get_by_text("Aguardando resposta do cliente").first.wait_for()
    attendance.refresh_from_db()
    assert attendance.status_attendance == "waiting_approval"

    # Cliente: aprova.
    client = sessions("cliente")
    client.login(customer)
    page = client.go(f"attendance.html?id={attendance.pk}")
    page.click("#ba")
    page.click("#cfa [data-yes]")
    page.wait_for_selector("#ba", state="detached")
    attendance.refresh_from_db()
    assert attendance.status_attendance == "approved"

    # Oficina: inicia, marca a execução, conclui e entrega.
    page = shop.go(f"w-attendance.html?id={attendance.pk}")
    page.click("#bs")
    item = attendance.budgets.get(status_budget="approved").items.get()
    page.click(f'[data-x="{item.pk}:executed"]')
    page.wait_for_selector("#bd:not([disabled])")
    page.click("#bd")
    page.click("#cfs [data-yes]")
    page.click("#bv")
    page.click("#cfs [data-yes]")
    page.get_by_text("Atendimento entregue.").wait_for()
    attendance.refresh_from_db()
    assert attendance.status_attendance == "delivered"
    assert RegisterMaintenance.objects.filter(
        attendance=attendance, budget_item=item
    ).exists()

    # Cliente: o serviço entra no histórico do veículo; avalia o atendimento.
    page = client.go(f"vehicle.html?id={vehicle.pk}")
    page.locator("#tl").get_by_text(item.description).first.wait_for()
    page = client.go(f"attendance.html?id={attendance.pk}")
    page.click("#bv")
    page.locator("label[for=rt5]").click()
    page.fill("#comment", "Serviço rápido e bem explicado.")
    page.get_by_role("button", name="Enviar avaliação").click()
    page.wait_for_selector("#bv", state="detached")
    review = Review.objects.get(budget__attendance=attendance)
    assert (review.rating, review.comment) == (5, "Serviço rápido e bem explicado.")

    # Oficina: resposta pública, visível no perfil.
    page = shop.go("w-reviews.html")
    page.click(f'[data-rs="{review.pk}"]')
    page.fill("#workshop_response", "Obrigado pela confiança!")
    page.get_by_role("button", name="Publicar resposta").click()
    page.get_by_text("Sua resposta:").wait_for()
    review.refresh_from_db()
    assert review.workshop_response == "Obrigado pela confiança!"

    visitor = sessions("visitante")
    page = visitor.go(f"shop.html?id={workshop.pk}")
    page.click("#t-r")
    page.locator("#tp").get_by_text("Obrigado pela confiança!").wait_for()


# ---------------------------------------------------------------- F5


def test_f5_chat_both_ways_with_polling(sessions):
    workshop = _workshop_near()
    customer = ClientFactory(name="Diego Alves")

    client = sessions("cliente")
    client.login(customer)
    page = client.go(f"shop.html?id={workshop.pk}")
    page.click("#bc")
    page.wait_for_url(re.compile(r"chat\.html\?id=\d+"))
    chat_id = int(page.url.rsplit("=", 1)[1])
    page.fill("#mi", "Olá! Vocês fazem alinhamento?")
    page.press("#mi", "Enter")
    page.get_by_text("Olá! Vocês fazem alinhamento?").first.wait_for()

    shop = sessions("oficina")
    shop.login(workshop, "workshop")
    page_w = shop.go(f"chat.html?id={chat_id}")
    page_w.get_by_text("Olá! Vocês fazem alinhamento?").first.wait_for()
    page_w.fill("#mi", "Fazemos sim, pode vir amanhã.")
    page_w.press("#mi", "Enter")

    # O cliente recebe pelo polling (5 s), sem recarregar a página.
    page.get_by_text("Fazemos sim, pode vir amanhã.").first.wait_for(timeout=20_000)


# ---------------------------------------------------------------- F6


def test_f6_promotion_and_advertisement_on_the_home(sessions):
    workshop = _workshop_near()
    service = WorkshopService.objects.get(workshop=workshop)
    PromotionFactory(
        workshop=workshop, workshop_service=service, title="Alinhamento com 20% off"
    )
    running = PromotionFactory(
        workshop=workshop, workshop_service=service, title="Semana do freio"
    )
    now = timezone.now()
    PromotionAdvertisementFactory(
        promotion=running,
        payment_status="paid",
        status_advertisement="active",
        date_start=now - timedelta(hours=1),
        date_end=now + timedelta(days=2),
    )

    visitor = sessions("visitante")
    page = visitor.go("index.html")
    promos = page.locator("#promos")
    promos.get_by_text("Alinhamento com 20% off").first.wait_for()
    promos.get_by_text("Semana do freio").first.wait_for()


# ---------------------------------------------------------------- F7


def test_f7_denunciation_and_moderation(sessions):
    from apps.moderation.services import moderate_denunciation

    workshop = _workshop_near()
    budget, *_ = deliver_attendance(AttendanceFactory(workshop=workshop))
    review = make_review(budget, comment="Comentário ofensivo aqui")
    reporter = ClientFactory()

    client = sessions("cliente")
    client.login(reporter)
    page = client.go(f"shop.html?id={workshop.pk}")
    page.click("#t-r")
    page.click(f'[data-rep="review:{review.pk}"]')
    page.locator(
        "label", has=page.locator("input[name=reason][value=offensive_language]")
    ).click()
    page.get_by_role("button", name="Enviar denúncia").click()
    page.wait_for_selector("#rf", state="detached")
    denunciation = Denunciation.objects.get(review=review, client=reporter)
    assert denunciation.status_denunciation == "pending"

    # Moderação (rotas /api/admin/*; a tela T27/T28 não existe): procede → avaliação oculta.
    moderate_denunciation(
        denunciation.pk, status="upheld", decision="Linguagem ofensiva"
    )
    page.reload()
    page.click("#t-r")
    page.wait_for_selector("#tp")
    page.wait_for_timeout(500)
    assert "Comentário ofensivo aqui" not in page.locator("#tp").inner_text()


# ---------------------------------------------------------------- F8


def test_f8_forbidden_pages_lead_to_login_or_403_without_leaking(sessions):
    workshop = _workshop_near()
    customer = ClientFactory()
    other = VehicleFactory(plate="ZZZ9Z99", model="Segredo")

    visitor = sessions("visitante")
    page = visitor.go("vehicles.html")
    page.wait_for_url("**/login.html?next=vehicles.html")
    page = visitor.go("w-attendances.html")
    page.wait_for_url("**/login.html?next=w-attendances.html")

    client = sessions("cliente")
    client.login(customer)
    page = client.go("w-attendances.html")
    page.wait_for_url("**/404.html?code=403")
    page = client.go(f"vehicle.html?id={other.pk}")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    assert "ZZZ-9Z99" not in body and "ZZZ9Z99" not in body and "Segredo" not in body

    shop = sessions("oficina")
    shop.login(workshop, "workshop")
    page = shop.go("vehicles.html")
    page.wait_for_url("**/404.html?code=403")

    # Sessão encerrada no servidor (expirou/derrubada): a próxima chamada dá 401 e a tela vai ao login.
    from django.contrib.sessions.models import Session

    Session.objects.all().delete()
    page = client.go("attendances.html")
    page.wait_for_url("**/login.html?next=attendances.html")


# ------------------------------------------------------- cenários de falha


def test_budget_expiring_while_the_page_is_open_shows_the_conflict(sessions):
    """Vencido ao abrir, a tela já mostra "Expirado" sem botões; aqui ele vence com a
    página aberta e o 409 do banco aparece na confirmação."""
    from apps.attendances.models import Budget

    customer = ClientFactory()
    attendance = AttendanceFactory(client=customer, workshop=_workshop_near())
    now = timezone.now()
    budget = BudgetFactory(
        attendance=attendance, date_creation=now - timedelta(days=10)
    )
    BudgetItemFactory(budget=budget)
    Attendance.objects.filter(pk=attendance.pk).update(
        status_attendance="waiting_approval"
    )

    client = sessions("cliente")
    client.login(customer)
    page = client.go(f"attendance.html?id={attendance.pk}")
    page.wait_for_selector("#ba")
    Budget.objects.filter(pk=budget.pk).update(
        date_validity=timezone.now() - timedelta(minutes=1)
    )

    page.click("#ba")
    page.click("#cfa [data-yes]")
    page.locator("#cfa [data-cerr]").get_by_text("fora da validade").wait_for()
    budget.refresh_from_db()
    assert budget.status_budget == "pending"


def test_duplicate_review_shows_the_conflict_message(sessions):
    customer = ClientFactory()
    attendance = AttendanceFactory(client=customer, workshop=_workshop_near())
    budget, *_ = deliver_attendance(attendance)

    client = sessions("cliente")
    client.login(customer)
    page = client.go(f"attendance.html?id={attendance.pk}")
    page.wait_for_selector("#bv")
    make_review(budget)  # avaliada em outra aba enquanto esta estava aberta

    page.click("#bv")
    page.locator("label[for=rt4]").click()
    page.get_by_role("button", name="Enviar avaliação").click()
    page.get_by_text("Você já avaliou este atendimento.").wait_for()
    assert Review.objects.filter(budget=budget).count() == 1
