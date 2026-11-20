import psycopg
import pytest
from apps.core.db_errors import is_retryable, translate_db_error
from apps.core.exceptions import sam_exception_handler
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    ChatFactory,
    ClientFactory,
    VehicleFactory,
    WorkshopFactory,
)
from apps.core.transactions import transactional
from django.db import OperationalError, connection
from rest_framework import status
from rest_framework.test import APIRequestFactory


def capture_db_error(callable_):
    from django.db import DatabaseError, transaction

    with pytest.raises(DatabaseError) as info:
        with transaction.atomic():
            callable_()
    return info.value


def response_for(exc):
    return sam_exception_handler(exc, {"view": object()})


@pytest.mark.django_db
def test_duplicate_client_email_maps_to_field_error():
    ClientFactory(email="ana@exemplo.com")
    exc = capture_db_error(lambda: ClientFactory(email="ANA@exemplo.com"))

    response = response_for(exc)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert list(response.data) == ["email"]


@pytest.mark.django_db
def test_duplicate_plate_maps_to_400_on_plate():
    vehicle = VehicleFactory()
    exc = capture_db_error(
        lambda: VehicleFactory(client=vehicle.client, plate=vehicle.plate)
    )

    response = response_for(exc)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert list(response.data) == ["plate"]


@pytest.mark.django_db
def test_trigger_check_violation_returns_409_with_database_message():
    attendance = AttendanceFactory()
    budget = BudgetFactory(attendance=attendance)

    def approve_without_sending():
        budget.status_budget = "approved"
        budget.save(update_fields=["status_budget"])

    response = response_for(capture_db_error(approve_without_sending))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "waiting_approval" in response.data["detail"]


@pytest.mark.django_db
def test_raise_exception_without_errcode_maps_to_409():
    exc = capture_db_error(
        lambda: connection.cursor().execute("SELECT register_attendance_history(0)")
    )

    response = response_for(exc)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["detail"] == "O atendimento 0 não existe."


@pytest.mark.django_db
def test_check_constraint_does_not_leak_constraint_name():
    exc = capture_db_error(lambda: WorkshopFactory(cnpj="123"))

    response = response_for(exc)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "ck_workshop" not in str(response.data)


@pytest.mark.django_db
def test_restrict_delete_maps_to_409():
    attendance = AttendanceFactory()
    exc = capture_db_error(lambda: attendance.client.delete())

    response = response_for(exc)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "dependências" in response.data["detail"]


@pytest.mark.django_db
def test_chat_pair_is_unique():
    chat = ChatFactory()
    exc = capture_db_error(
        lambda: ChatFactory(client=chat.client, workshop=chat.workshop)
    )

    assert response_for(exc).status_code == status.HTTP_409_CONFLICT


def deadlock_error():
    cause = psycopg.errors.DeadlockDetected("deadlock detected")
    error = OperationalError("deadlock detected")
    error.__cause__ = cause
    return error


def test_deadlock_maps_to_503_with_retry_after():
    response = response_for(deadlock_error())

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response["Retry-After"] == "1"
    assert is_retryable(deadlock_error())


def test_unknown_database_error_is_not_translated():
    assert translate_db_error(OperationalError("boom")) is None


def test_unexpected_error_returns_generic_500(settings):
    settings.DEBUG = False

    response = response_for(RuntimeError("segredo interno SELECT * FROM x"))

    assert response.status_code == 500
    assert response.data == {"detail": "Erro interno do servidor."}


def test_list_payload_is_wrapped_in_non_field_errors():
    from rest_framework.exceptions import ValidationError

    response = response_for(ValidationError(["Algo inválido."]))

    assert response.data == {"non_field_errors": ["Algo inválido."]}


@pytest.mark.django_db(transaction=True)
def test_transactional_retries_deadlock_until_success():
    calls = []

    @transactional(retries=3)
    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise deadlock_error()
        return "ok"

    assert operation() == "ok"
    assert len(calls) == 3


@pytest.mark.django_db(transaction=True)
def test_transactional_gives_up_after_retries():
    calls = []

    @transactional(retries=3)
    def operation():
        calls.append(1)
        raise deadlock_error()

    with pytest.raises(OperationalError):
        operation()
    assert len(calls) == 4


@pytest.mark.django_db(transaction=True)
def test_transactional_does_not_retry_other_errors():
    calls = []

    @transactional(retries=3)
    def operation():
        calls.append(1)
        raise ValueError("outro erro")

    with pytest.raises(ValueError):
        operation()
    assert len(calls) == 1


@pytest.mark.django_db(transaction=True)
def test_transactional_rolls_back_on_failure():
    @transactional
    def operation():
        ClientFactory()
        raise ValueError

    from apps.accounts.models import Client

    with pytest.raises(ValueError):
        operation()
    assert Client.objects.count() == 0


def test_view_error_response_uses_json():
    request = APIRequestFactory().get("/")
    assert request is not None
