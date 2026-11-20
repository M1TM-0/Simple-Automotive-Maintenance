"""Histórico, avaliação, horários e solicitações de serviço (init.sql 9.1, 9.2, 9.4,
9.7; RB-15…RB-20)."""

import pytest
from apps.catalog.models import Service, WorkshopService
from apps.core.tests.factories import (
    OperationHourFactory,
    ProductFactory,
    RegisterMaintenanceFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    WorkshopFactory,
    WorkshopServiceFactory,
    make_review,
)
from apps.reviews.models import Review
from apps.vehicles.models import RegisterMaintenance, RegisterMaintenancePart
from apps.workshops.models import OperationHour

from .support import (
    CHECK,
    FOREIGN_KEY,
    RAISE,
    UNIQUE,
    attendance_at,
    covers,
    scalar,
    set_budget,
    set_execution,
    set_status,
    violates,
)

pytestmark = [pytest.mark.db_rules, pytest.mark.django_db]

INSERT_SERVICE_RECORD = """
    INSERT INTO register_maintenance (id_vehicle, id_attendance, id_budget, id_budget_item,
                                      service_name, date_maintenance, mileage_km)
    VALUES (%s, %s, %s, %s, 'Troca de óleo', NOW(), 1000) RETURNING id_register_maintenance
"""
INSERT_PART_RECORD = """
    INSERT INTO register_maintenance_part (id_vehicle, id_attendance, id_budget, id_workshop,
        id_budget_item, id_service_item, id_product, description, quantity, unit_price,
        date_maintenance, mileage_km)
    VALUES (%s, %s, %s, %s, %s, %s, %s, 'Filtro', 1, 10, NOW(), 1000)
    RETURNING id_register_maintenance_part
"""


def _service_record_params(case):
    item = case.items[0]
    return [case.attendance.vehicle_id, case.attendance.pk, case.budget.pk, item.pk]


class TestHistoryOriginGuards:
    """`trg_rm_origin_guard`, `trg_rmp_origin_guard` e `trg_rmp_item_match`."""

    @covers(
        "trg_rm_origin_guard",
        "trg_rmp_origin_guard",
        "trg_rmp_item_match",
        positive=True,
    )
    def test_delivery_and_manual_records_are_accepted(self):
        case = attendance_at("delivered", history_items=True)
        assert (
            RegisterMaintenance.objects.filter(attendance=case.attendance).count() == 1
        )
        part = RegisterMaintenancePart.objects.get(attendance=case.attendance)
        assert part.product_id == case.items[1].product_id

        manual = RegisterMaintenanceFactory(vehicle=case.attendance.vehicle)
        assert manual.budget_item_id is None

    @covers("trg_rm_origin_guard", negative=True)
    def test_service_record_requires_a_delivered_attendance(self):
        case = attendance_at("in_progress", history_items=True)
        set_execution(case.items[0], "executed")
        set_execution(case.items[1], "executed")
        set_status(case.attendance, "completed")
        with violates(
            CHECK,
            "O histórico só pode ser registrado para atendimento entregue (status atual: completed).",
        ):
            scalar(INSERT_SERVICE_RECORD, _service_record_params(case))

    @covers("trg_rm_origin_guard", negative=True)
    def test_service_record_requires_an_approved_budget(self):
        case = attendance_at("in_progress", history_items=True)
        set_execution(case.items[0], "executed")
        set_status(case.attendance, "canceled")  # o orçamento aprovado vira cancelado
        with violates(
            CHECK, "O histórico exige orçamento aprovado (status atual: cancelled)."
        ):
            scalar(INSERT_SERVICE_RECORD, _service_record_params(case))

    @covers("trg_rmp_origin_guard", negative=True)
    def test_part_record_requires_a_delivered_attendance(self):
        case = attendance_at("in_progress", history_items=True)
        for item in case.items:
            set_execution(item, "executed")
        set_status(case.attendance, "completed")
        part = case.items[1]
        params = [
            case.attendance.vehicle_id,
            case.attendance.pk,
            case.budget.pk,
            case.attendance.workshop_id,
            part.pk,
            part.service_item_id,
            part.product_id,
        ]
        with violates(
            CHECK,
            "O histórico só pode ser registrado para atendimento entregue (status atual: completed).",
        ):
            scalar(INSERT_PART_RECORD, params)

    @covers("trg_rmp_item_match", negative=True)
    def test_part_must_match_the_product_of_its_item(self):
        case = attendance_at("delivered", history_items=True)
        part = case.items[1]
        other_product = ProductFactory(workshop=case.attendance.workshop)
        params = [
            case.attendance.vehicle_id,
            case.attendance.pk,
            case.budget.pk,
            case.attendance.workshop_id,
            part.pk,
            part.service_item_id,
            other_product.pk,
        ]
        with violates(
            CHECK,
            f"O produto/serviço de origem da peça registrada difere do item de orçamento {part.pk}.",
        ):
            scalar(INSERT_PART_RECORD, params)


class TestReviewTrigger:
    """`trg_validate_review_budget`: só depois da entrega e com orçamento aprovado."""

    @covers("trg_validate_review_budget", positive=True)
    def test_review_after_delivery(self):
        case = attendance_at("delivered")
        review = make_review(case.budget)
        assert Review.objects.filter(pk=review.pk).exists()

    @covers("trg_validate_review_budget", negative=True)
    @pytest.mark.parametrize("status", ["approved", "in_progress", "completed"])
    def test_review_before_delivery_is_refused(self, status):
        case = attendance_at(status)
        with violates(
            CHECK,
            f"A avaliação só pode ser realizada após a entrega do veículo (atendimento: {status}).",
        ):
            make_review(case.budget)

    @covers("trg_validate_review_budget", negative=True)
    def test_review_requires_an_approved_budget(self):
        case = attendance_at("waiting_approval")
        set_budget(case.budget, "rejected")
        with violates(
            CHECK, "A avaliação exige um orçamento aprovado (status atual: rejected)."
        ):
            make_review(case.budget)

    @covers("trg_validate_review_budget", negative=True)
    def test_review_of_a_missing_budget(self):
        with violates(FOREIGN_KEY, "O orçamento informado não existe."):
            scalar(
                "INSERT INTO review (id_review, id_budget, rating) VALUES (gen_random_uuid(), 0, 5) RETURNING 1"
            )

    def test_one_review_per_budget(self):
        case = attendance_at("delivered")
        make_review(case.budget)
        with violates(UNIQUE):
            make_review(case.budget)


class TestOperationHours:
    """`trg_operation_hour_no_overlap`."""

    @covers("trg_operation_hour_no_overlap", positive=True)
    def test_consecutive_intervals_and_other_days_are_fine(self):
        workshop = WorkshopFactory()
        OperationHourFactory(
            workshop=workshop, day_of_week=1, opening_time="08:00", closing_time="12:00"
        )
        OperationHourFactory(
            workshop=workshop, day_of_week=1, opening_time="12:00", closing_time="18:00"
        )
        OperationHourFactory(
            workshop=workshop, day_of_week=2, opening_time="10:00", closing_time="11:00"
        )
        OperationHourFactory(
            day_of_week=1, opening_time="09:00", closing_time="10:00"
        )  # outra oficina
        assert OperationHour.objects.filter(workshop=workshop).count() == 3

    @covers("trg_operation_hour_no_overlap", negative=True)
    def test_overlapping_insert_is_refused(self):
        workshop = WorkshopFactory()
        OperationHourFactory(
            workshop=workshop, day_of_week=3, opening_time="08:00", closing_time="12:00"
        )
        with violates(
            CHECK,
            "O intervalo 11:00:00-13:00:00 se sobrepõe a outro intervalo da oficina no mesmo dia.",
        ):
            OperationHourFactory(
                workshop=workshop,
                day_of_week=3,
                opening_time="11:00",
                closing_time="13:00",
            )

    @covers("trg_operation_hour_no_overlap", negative=True)
    def test_overlapping_update_is_refused(self):
        workshop = WorkshopFactory()
        OperationHourFactory(
            workshop=workshop, day_of_week=4, opening_time="08:00", closing_time="12:00"
        )
        afternoon = OperationHourFactory(
            workshop=workshop, day_of_week=4, opening_time="13:00", closing_time="18:00"
        )
        with violates(CHECK, "se sobrepõe"):
            OperationHour.objects.filter(pk=afternoon.pk).update(opening_time="11:30")


class TestServiceRequests:
    """`trg_workshop_service_default_request`, `approve_/reject_workshop_service_request`,
    `clean_service_name` e `normalize_service_name`."""

    def _request(self, name="Polimento técnico", **kwargs):
        return WorkshopServiceFactory(
            service=None,
            name_local=name,
            suggested_category=ServiceCategoryFactory(),
            **kwargs,
        )

    @covers("trg_workshop_service_default_request", positive=True)
    def test_custom_service_is_born_pending(self):
        request = WorkshopService.objects.create(
            workshop=WorkshopFactory(),
            name_local="Polimento técnico",
            suggested_category=ServiceCategoryFactory(),
            price_base="10.00",
            duration_estimate=10,
        )
        request.refresh_from_db()
        assert request.status_solicitation == "pending"

    @covers("trg_workshop_service_default_request", negative=True)
    def test_catalog_service_has_no_request(self):
        service = WorkshopServiceFactory()
        service.refresh_from_db()
        assert service.status_solicitation is None

    @covers("approve_workshop_service_request", positive=True)
    def test_approval_creates_a_global_service(self):
        request = self._request("Polimento")
        category = ServiceCategoryFactory()
        service_id = scalar(
            "SELECT approve_workshop_service_request(%s, %s, %s)",
            [request.pk, category.pk, "  Polimento   técnico "],
        )
        request.refresh_from_db()
        service = Service.objects.get(pk=service_id)
        assert (service.name, service.category_id) == ("Polimento técnico", category.pk)
        assert (request.status_solicitation, request.service_id) == (
            "approved",
            service_id,
        )

    @covers("approve_workshop_service_request", positive=True)
    def test_approval_reuses_the_same_normalized_name_keeping_its_category(self):
        existing = ServiceFactory(name="Lavagem de motor")
        request = self._request("LAVAGEM DE MOTOR")
        service_id = scalar(
            "SELECT approve_workshop_service_request(%s, %s)",
            [request.pk, ServiceCategoryFactory().pk],
        )
        existing.refresh_from_db()
        assert service_id == existing.pk
        assert existing.name == "Lavagem de motor"

    @covers("approve_workshop_service_request", negative=True)
    def test_only_pending_requests_are_approved(self):
        request = self._request()
        scalar(
            "SELECT approve_workshop_service_request(%s, %s)",
            [request.pk, ServiceCategoryFactory().pk],
        )
        with violates(
            RAISE,
            "Somente solicitações pendentes podem ser aprovadas (status atual: approved).",
        ):
            scalar("SELECT approve_workshop_service_request(%s)", [request.pk])

    @covers("approve_workshop_service_request", negative=True)
    def test_catalog_service_is_not_a_request(self):
        service = WorkshopServiceFactory()
        with violates(RAISE, "(status atual: serviço do catálogo)"):
            scalar("SELECT approve_workshop_service_request(%s)", [service.pk])

    @covers("approve_workshop_service_request", negative=True)
    def test_new_global_service_needs_a_category(self):
        request = WorkshopServiceFactory(
            service=None, name_local="Serviço sem categoria", suggested_category=None
        )
        with violates(RAISE, "Informe a categoria do novo serviço global."):
            scalar("SELECT approve_workshop_service_request(%s)", [request.pk])

    @covers("approve_workshop_service_request", negative=True)
    def test_workshop_already_has_the_global_service(self):
        global_service = ServiceFactory(name="Alinhamento 3D")
        owned = WorkshopServiceFactory(service=global_service)
        request = self._request("alinhamento 3d", workshop=owned.workshop)
        with violates(UNIQUE, "A oficina já possui o serviço global"):
            scalar("SELECT approve_workshop_service_request(%s)", [request.pk])
        request.refresh_from_db()
        assert request.status_solicitation == "pending"

    @covers("approve_workshop_service_request", negative=True)
    def test_unknown_request(self):
        with violates(RAISE, "Serviço da oficina 0 não encontrado."):
            scalar("SELECT approve_workshop_service_request(0)")

    @covers("reject_workshop_service_request", positive=True)
    def test_rejection_keeps_the_motivation(self):
        request = self._request()
        scalar(
            "SELECT reject_workshop_service_request(%s, %s) IS NULL",
            [request.pk, "Duplicado"],
        )
        request.refresh_from_db()
        assert (request.status_solicitation, request.motivation_rejection) == (
            "rejected",
            "Duplicado",
        )
        assert request.date_solicitation_response is not None

    @covers("reject_workshop_service_request", negative=True)
    @pytest.mark.parametrize("motivation", [None, "", "   "])
    def test_rejection_needs_a_motivation(self, motivation):
        request = self._request()
        with violates(RAISE, "Informe o motivo da rejeição."):
            scalar(
                "SELECT reject_workshop_service_request(%s, %s) IS NULL",
                [request.pk, motivation],
            )

    @covers("reject_workshop_service_request", negative=True)
    def test_only_pending_requests_are_rejected(self):
        request = self._request()
        scalar("SELECT reject_workshop_service_request(%s, 'x') IS NULL", [request.pk])
        with violates(
            RAISE,
            "Somente solicitações pendentes podem ser rejeitadas (status atual: rejected).",
        ):
            scalar(
                "SELECT reject_workshop_service_request(%s, 'y') IS NULL", [request.pk]
            )

    @covers("clean_service_name", "normalize_service_name", positive=True)
    def test_name_cleaning_and_normalization(self):
        assert (
            scalar("SELECT clean_service_name(%s)", ["  Troca   de\tÓleo "])
            == "Troca de Óleo"
        )
        assert (
            scalar("SELECT normalize_service_name(%s)", ["  Troca   de\tÓleo "])
            == "troca de óleo"
        )

    @covers("clean_service_name", "normalize_service_name", negative=True)
    def test_normalization_keeps_accents_and_null(self):
        """Compara texto, não significado: "óleo" e "oleo" continuam distintos (STRICT: NULL → NULL)."""
        assert (
            scalar(
                "SELECT normalize_service_name('Óleo') = normalize_service_name('oleo')"
            )
            is False
        )
        assert scalar("SELECT clean_service_name(NULL) IS NULL") is True
        assert scalar("SELECT normalize_service_name(NULL) IS NULL") is True
