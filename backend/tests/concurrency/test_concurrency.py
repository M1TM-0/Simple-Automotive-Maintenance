"""BE-080 — Concorrência e deadlock nos pontos críticos.

Cada cenário dispara as operações em threads com conexões próprias, liberadas
juntas por uma barreira, e é repetido `SAM_CONCURRENCY_ROUNDS` vezes (padrão 5; o CI
noturno pode subir) para expor intermitência. O banco é o real (READ COMMITTED,
locks ordenados do `init.sql`); nada é simulado, nem o deadlock.
"""

import os
import random
import threading
import time
from datetime import timedelta

import pytest
from apps.attendances.models import Budget
from apps.attendances.services import respond_budget
from apps.catalog.models import WorkshopService
from apps.chat.models import Chat
from apps.chat.services import open_chat
from apps.core.management.commands.run_expiration_jobs import run_once
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    ClientFactory,
    PagWorkshopFactory,
    ServiceCategoryFactory,
    VehicleFactory,
    WorkshopFactory,
    WorkshopServiceFactory,
)
from apps.core.transactions import transactional
from apps.moderation.services import approve_service_request
from apps.reviews.models import Review
from apps.reviews.services import create_review
from apps.vehicles.models import Vehicle
from django.db import connection, connections
from django.db.models import F

from tests.db_rules.support import attendance_at, set_status

ROUNDS = range(int(os.environ.get("SAM_CONCURRENCY_ROUNDS", "5")))

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


def run_concurrently(*calls, timeout=30):
    """Executa as chamadas ao mesmo tempo (uma conexão por thread).

    Devolve `(resultados, erros)`, cada um na ordem em que terminou.
    """
    barrier = threading.Barrier(len(calls))
    results, errors = [], []
    lock = threading.Lock()

    def worker(call):
        try:
            barrier.wait(timeout=timeout)
            value = call()
            with lock:
                results.append(value)
        except Exception as exc:  # noqa: BLE001 — o teste inspeciona as exceções
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)
    assert not any(thread.is_alive() for thread in threads), (
        "thread presa (lock não liberado?)"
    )
    return results, errors


def http_status(exc):
    """Status que a API daria ao erro (o tratador traduz os erros do banco: 409/503)."""
    from apps.core.exceptions import sam_exception_handler

    response = sam_exception_handler(exc, {})
    return response.status_code if response is not None else 500


def _db_clock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        return cursor.fetchone()[0]


# --------------------------------------------------------- aprovar × expirar


@pytest.mark.parametrize("round_", ROUNDS)
def test_approve_and_expire_at_the_deadline_never_both_win(round_):
    """Orçamento aguardando aprovação com validade vencendo agora: o cliente aprova
    enquanto a rotina expira. No máximo um vence; o estado final é coerente."""
    attendance = AttendanceFactory()
    validity = _db_clock() + timedelta(milliseconds=400)
    budget = BudgetFactory(attendance=attendance, date_validity=validity)
    BudgetItemFactory(budget=budget)
    set_status(attendance, "waiting_approval")

    # Libera as duas operações em torno do vencimento (± alguns ms, varia por rodada).
    time.sleep(
        max(0.0, (validity - _db_clock()).total_seconds() + random.uniform(-0.02, 0.02))
    )
    results, errors = run_concurrently(
        lambda: respond_budget(budget, approve=True), run_once
    )

    approved = any(isinstance(r, Budget) for r in results)
    assert [http_status(e) for e in errors] in ([], [409]), errors

    run_once()  # se a rotina pulou a linha travada (SKIP LOCKED), a próxima execução resolve
    budget.refresh_from_db()
    attendance.refresh_from_db()
    if approved:
        assert (budget.status_budget, attendance.status_attendance) == (
            "approved",
            "approved",
        )
    else:
        assert (budget.status_budget, attendance.status_attendance) == (
            "expired",
            "requested",
        )


@pytest.mark.parametrize("round_", ROUNDS)
def test_two_approvals_of_the_same_budget_succeed_once(round_):
    case = attendance_at("waiting_approval")

    results, errors = run_concurrently(
        lambda: respond_budget(case.budget, approve=True),
        lambda: respond_budget(case.budget, approve=True),
    )

    assert len(results) == 1 and len(errors) == 1
    assert http_status(errors[0]) == 409
    case.refresh()
    assert (case.budget.status_budget, case.attendance.status_attendance) == (
        "approved",
        "approved",
    )


@pytest.mark.parametrize("round_", ROUNDS)
def test_approve_and_reject_at_the_same_time_leave_one_answer(round_):
    case = attendance_at("waiting_approval")

    results, errors = run_concurrently(
        lambda: respond_budget(case.budget, approve=True),
        lambda: respond_budget(case.budget, approve=False),
    )

    assert len(results) == 1 and len(errors) == 1
    assert http_status(errors[0]) == 409
    case.refresh()
    expected = {"approved": "approved", "rejected": "requested"}
    assert case.attendance.status_attendance == expected[case.budget.status_budget]


# ---------------------------------------------------------------- chat e avaliação


@pytest.mark.parametrize("round_", ROUNDS)
def test_simultaneous_open_creates_one_chat(round_):
    client = ClientFactory()
    workshop = PagWorkshopFactory().workshop

    results, errors = run_concurrently(*[lambda: open_chat(client.pk, workshop.pk)] * 4)

    assert not errors, errors
    assert len({chat.pk for chat, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    assert Chat.objects.filter(client=client, workshop=workshop).count() == 1


@pytest.mark.parametrize("round_", ROUNDS)
def test_duplicate_review_is_refused_once(round_):
    case = attendance_at("delivered")
    data = {"id_budget": case.budget.pk, "rating": 5}
    client_id = case.attendance.client_id

    results, errors = run_concurrently(
        lambda: create_review(client_id, data), lambda: create_review(client_id, data)
    )

    assert len(results) == 1 and len(errors) == 1
    assert http_status(errors[0]) == 409, (
        errors
    )  # pela checagem ou pelo `review_id_budget_key`
    assert Review.objects.filter(budget=case.budget).count() == 1


@pytest.mark.parametrize("round_", ROUNDS)
def test_two_approvals_of_the_same_service_request(round_):
    request = WorkshopServiceFactory(
        workshop=WorkshopFactory(),
        service=None,
        name_local=f"Vitrificação {round_}",
        suggested_category=ServiceCategoryFactory(),
        status_solicitation="pending",
    )

    results, errors = run_concurrently(
        lambda: approve_service_request(request.pk),
        lambda: approve_service_request(request.pk),
    )

    assert len(results) == 1 and len(errors) == 1
    assert http_status(errors[0]) == 409
    request.refresh_from_db()
    assert request.status_solicitation == "approved"
    assert WorkshopService.objects.filter(service_id=request.service_id).count() == 1


# --------------------------------------------------------------- deadlock


def test_real_deadlock_is_retried_by_transactional():
    """Duas transações travam duas linhas em ordens opostas: o PostgreSQL detecta o
    deadlock (40P01) e aborta uma; `@transactional` (BE-017) a repete e ambas concluem."""
    client = ClientFactory()
    first, second = VehicleFactory(client=client), VehicleFactory(client=client)
    barrier = threading.Barrier(2)
    attempts = {"a": 0, "b": 0}

    def locker(name, one, other):
        @transactional
        def work():
            attempts[name] += 1
            Vehicle.objects.select_for_update().get(pk=one)
            if attempts[name] == 1:
                barrier.wait(
                    timeout=10
                )  # as duas seguram a 1ª linha antes de pedir a 2ª
            Vehicle.objects.select_for_update().get(pk=other)
            Vehicle.objects.filter(pk__in=[one, other]).update(
                mileage_km=F("mileage_km") + 1
            )
            return name

        return work

    results, errors = run_concurrently(
        locker("a", first.pk, second.pk), locker("b", second.pk, first.pk), timeout=30
    )

    assert not errors, errors
    assert sorted(results) == ["a", "b"]
    assert sorted(attempts.values()) == [1, 2], (
        "exatamente uma transação foi abortada e repetida"
    )
    first.refresh_from_db()
    assert first.mileage_km == 50002  # as duas atualizações valeram


def test_deadlock_beyond_the_retries_is_503(monkeypatch):
    """Sem tentativas sobrando, o 40P01 sobe e a API responde 503 com Retry-After."""
    from apps.core.exceptions import sam_exception_handler
    from django.db import OperationalError

    client = ClientFactory()
    first, second = VehicleFactory(client=client), VehicleFactory(client=client)
    barrier = threading.Barrier(2)

    def locker(one, other):
        @transactional(retries=0)
        def work():
            Vehicle.objects.select_for_update().get(pk=one)
            barrier.wait(timeout=10)
            Vehicle.objects.select_for_update().get(pk=other)

        return work

    results, errors = run_concurrently(
        locker(first.pk, second.pk), locker(second.pk, first.pk)
    )

    assert len(results) == 1 and len(errors) == 1
    assert isinstance(errors[0], OperationalError)
    response = sam_exception_handler(errors[0], {})
    assert response.status_code == 503 and response["Retry-After"] == "1"
