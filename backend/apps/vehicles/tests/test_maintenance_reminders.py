"""BE-077: próximas manutenções (cálculo e API) e lembretes de manutenção preventiva."""

import threading
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from apps.core.tests.factories import (
    AttendanceFactory,
    ClientFactory,
    VehicleFactory,
    deliver_attendance,
    make_ready_workshop,
)
from apps.notifications.models import Notification
from apps.vehicles.models import MaintenanceReminder, RegisterMaintenance, Vehicle
from apps.vehicles.reminders import Execution, send_due_reminders, upcoming_maintenance
from django.core.management import call_command
from django.db import connections
from django.utils import timezone

DAY = datetime(2026, 1, 10, 12, tzinfo=UTC)


def execution(
    record_id, name="Troca de óleo", *, km, interval=None, days=0, service_id=None
):
    return Execution(
        record_id, name, DAY + timedelta(days=days), km, interval, service_id
    )


# ------------------------------------------------------------ cálculo (puro)


class TestCalculation:
    def test_acceptance_example_is_soon(self):
        """Critério: última troca a 40.000 km, intervalo 10.000, km atual 49.500 → aviso."""
        [item] = upcoming_maintenance(
            [execution(1, km=40_000, interval=10_000)], 49_500
        )

        assert (
            item.next_mileage_km,
            item.remaining_km,
            item.progress_percent,
            item.status,
        ) == (
            50_000,
            500,
            95,
            "soon",
        )
        assert (
            item.last_record_id,
            item.last_mileage_km,
            item.interval_km,
            item.current_mileage_km,
        ) == (
            1,
            40_000,
            10_000,
            49_500,
        )

    @pytest.mark.parametrize(
        ("current", "status", "remaining", "progress"),
        [
            (40_000, "ok", 10_000, 0),
            (48_999, "ok", 1_001, 89),
            (49_000, "soon", 1_000, 90),
            (50_000, "overdue", 0, 100),
            (51_200, "overdue", -1_200, 100),
        ],
    )
    def test_status_by_remaining_km(self, current, status, remaining, progress):
        [item] = upcoming_maintenance(
            [execution(1, km=40_000, interval=10_000)], current
        )
        assert (item.status, item.remaining_km, item.progress_percent) == (
            status,
            remaining,
            progress,
        )

    def test_threshold_follows_the_setting(self, settings):
        settings.SAM_MAINTENANCE_REMINDER_PERCENT = 25
        [item] = upcoming_maintenance(
            [execution(1, km=40_000, interval=10_000)], 47_600
        )
        assert item.status == "soon"

    def test_last_execution_counts_and_keeps_the_last_known_interval(self):
        """A oficina não informa intervalo: a troca feita por ela reinicia o ciclo com o intervalo do cliente."""
        history = [
            execution(1, km=40_000, interval=10_000, service_id=7),
            execution(2, "Troca de óleo 5W30", km=50_100, days=180, service_id=7),
        ]

        [item] = upcoming_maintenance(history, 52_000)

        assert (
            item.last_record_id,
            item.service_name,
            item.next_mileage_km,
            item.remaining_km,
        ) == (
            2,
            "Troca de óleo 5W30",
            60_100,
            8_100,
        )
        assert item.status == "ok"

    def test_newer_interval_replaces_the_older(self):
        history = [
            execution(1, km=40_000, interval=10_000),
            execution(2, km=50_000, interval=5_000, days=90),
        ]
        [item] = upcoming_maintenance(history, 50_000)
        assert (item.interval_km, item.next_mileage_km) == (5_000, 55_000)

    def test_items_group_by_catalog_service_or_normalized_name(self):
        history = [
            execution(1, "troca  de ÓLEO", km=40_000, interval=10_000),
            execution(2, "Troca de óleo", km=45_000, days=30),
            execution(3, "Pastilhas de freio", km=30_000, interval=30_000),
            execution(
                4, "Pastilhas de freio", km=44_000, interval=20_000, service_id=9
            ),
        ]

        items = upcoming_maintenance(history, 46_000)

        assert [(i.last_record_id, i.next_mileage_km) for i in items] == [
            (2, 55_000),
            (3, 60_000),
            (4, 64_000),
        ]

    def test_items_without_interval_or_without_km_are_left_out(self):
        history = [
            execution(1, "Alinhamento", km=40_000),  # sem intervalo
            execution(2, km=40_000, interval=10_000),
            execution(3, km=None, days=10),  # a última troca não tem km: sem base
            execution(4, "Bateria", km=None, interval=40_000),
        ]
        assert upcoming_maintenance(history, 49_500) == []

    def test_vehicle_mileage_below_the_last_execution_uses_the_execution(self):
        [item] = upcoming_maintenance([execution(1, km=40_000, interval=10_000)], None)
        assert (item.current_mileage_km, item.remaining_km, item.progress_percent) == (
            40_000,
            10_000,
            0,
        )
        [item] = upcoming_maintenance(
            [execution(1, km=40_000, interval=10_000)], 39_000
        )
        assert item.current_mileage_km == 40_000

    def test_most_urgent_first(self):
        history = [
            execution(1, "Pneus", km=10_000, interval=45_000),
            execution(2, "Troca de óleo", km=40_000, interval=10_000),
            execution(3, "Correia dentada", km=0, interval=45_000),
        ]
        names = [i.service_name for i in upcoming_maintenance(history, 49_500)]
        assert names == ["Correia dentada", "Troca de óleo", "Pneus"]


# ---------------------------------------------------------------- helpers DB


def manual(
    vehicle, name="Troca de óleo", *, km, interval=None, days_ago=0, service=None
):
    return RegisterMaintenance.objects.create(
        vehicle=vehicle,
        service=service,
        service_name=name,
        date_maintenance=timezone.now() - timedelta(days=days_ago),
        mileage_km=km,
        interval_km=interval,
    )


def set_mileage(vehicle, km):
    Vehicle.objects.filter(pk=vehicle.pk).update(mileage_km=km)
    vehicle.refresh_from_db()


def run_reminders():
    out = StringIO()
    call_command("send_maintenance_reminders", stdout=out)
    return out.getvalue()


def notifications(client):
    return list(
        Notification.objects.filter(client=client)
        .order_by("id_notification")
        .values_list("title", "message", "url")
    )


# ------------------------------------------------------------------------ API


@pytest.mark.django_db
class TestUpcomingApi:
    def url(self, vehicle):
        return f"/api/vehicles/{vehicle.pk}/upcoming-maintenance/"

    def test_lists_items_with_the_calculation(self, client_session, client_account):
        vehicle = VehicleFactory(client=client_account, mileage_km=49_500)
        record = manual(vehicle, km=40_000, interval=10_000, days_ago=200)
        manual(vehicle, "Alinhamento", km=45_000)  # sem intervalo: fora

        response = client_session.get(self.url(vehicle))

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        item = body["results"][0]
        assert item == {
            "id": f"service-{record.pk}",
            "id_service": None,
            "service_name": "Troca de óleo",
            "last_date": item["last_date"],
            "last_mileage_km": 40_000,
            "interval_km": 10_000,
            "next_mileage_km": 50_000,
            "current_mileage_km": 49_500,
            "remaining_km": 500,
            "progress_percent": 95,
            "status": "soon",
            "reminder_sent_at": None,
        }

    def test_manual_record_with_interval_through_the_api(
        self, client_session, client_account
    ):
        """Fluxo da tela T12: registrar com "próxima troca em km" e acompanhar o prazo."""
        vehicle = VehicleFactory(client=client_account, mileage_km=40_000)
        response = client_session.post(
            f"/api/vehicles/{vehicle.pk}/history/",
            {
                "service_name": "Troca de óleo",
                "date_maintenance": "2026-01-10",
                "mileage_km": 40_000,
                "interval_km": 10_000,
            },
            format="json",
        )
        assert response.status_code == 201

        assert (
            client_session.get(self.url(vehicle)).json()["results"][0]["status"] == "ok"
        )
        client_session.patch(
            f"/api/vehicles/{vehicle.pk}/", {"mileage_km": 50_300}, format="json"
        )
        item = client_session.get(self.url(vehicle)).json()["results"][0]
        assert (item["status"], item["remaining_km"]) == ("overdue", -300)

    def test_workshop_execution_restarts_the_cycle(
        self, client_session, client_account
    ):
        workshop = make_ready_workshop()
        attendance = AttendanceFactory(
            client=client_account, workshop=workshop, mileage_km=50_100
        )
        vehicle = attendance.vehicle
        budget, service_item, _ = deliver_attendance(attendance)
        service = service_item.workshop_service.service
        manual(
            vehicle,
            service.name,
            km=40_000,
            interval=10_000,
            days_ago=300,
            service=service,
        )
        set_mileage(vehicle, 51_000)

        [item] = client_session.get(self.url(vehicle)).json()["results"]

        delivered = RegisterMaintenance.objects.get(budget_item=service_item)
        assert item["id"] == f"service-{delivered.pk}"
        assert (
            item["id_service"],
            item["last_mileage_km"],
            item["next_mileage_km"],
            item["status"],
        ) == (
            service.pk,
            50_100,
            60_100,
            "ok",
        )

    def test_access_matrix(self, api_client, client_session, ready_workshop_session):
        other = VehicleFactory()
        assert client_session.get(self.url(other)).status_code == 404
        assert api_client.get(self.url(other)).status_code == 401
        assert ready_workshop_session.get(self.url(other)).status_code == 403
        assert (
            client_session.get("/api/vehicles/999999/upcoming-maintenance/").status_code
            == 404
        )


# ------------------------------------------------------------------ lembretes


@pytest.mark.django_db
class TestReminderJob:
    def test_sends_once_per_cycle(
        self, client_account, client_session, django_capture_on_commit_callbacks
    ):
        """Critérios: gera o aviso e não repete (nem quando a manutenção passa a vencida)."""
        vehicle = VehicleFactory(
            client=client_account,
            brand="Fiat",
            model="Uno",
            plate="ABC1D23",
            mileage_km=49_500,
        )
        record = manual(vehicle, km=40_000, interval=10_000, days_ago=200)

        with django_capture_on_commit_callbacks(execute=True):
            assert "enviados: 1" in run_reminders()

        [(title, message, url)] = notifications(client_account)
        assert title == "Manutenção próxima"
        assert message.startswith(
            "Troca de óleo do Fiat Uno (ABC1D23): faltam 500 km (prevista aos 50.000 km)."
        )
        assert url == f"vehicle.html?id={vehicle.pk}"
        reminder = MaintenanceReminder.objects.get(register_maintenance=record)
        assert (reminder.due_mileage_km, reminder.status_reminder) == (50_000, "soon")
        sent_at = client_session.get(
            f"/api/vehicles/{vehicle.pk}/upcoming-maintenance/"
        ).json()["results"][0]["reminder_sent_at"]
        assert sent_at is not None

        set_mileage(vehicle, 51_000)
        with django_capture_on_commit_callbacks(execute=True):
            assert "enviados: 0" in run_reminders()
            assert "enviados: 0" in run_reminders()
        assert len(notifications(client_account)) == 1

    def test_new_execution_opens_a_new_cycle(
        self, client_account, django_capture_on_commit_callbacks
    ):
        vehicle = VehicleFactory(client=client_account, mileage_km=49_500)
        manual(vehicle, km=40_000, interval=10_000, days_ago=200)
        with django_capture_on_commit_callbacks(execute=True):
            send_due_reminders()

        manual(
            vehicle, km=50_200, days_ago=1
        )  # trocou o óleo (sem repetir o intervalo)
        set_mileage(vehicle, 55_000)
        with django_capture_on_commit_callbacks(execute=True):
            assert send_due_reminders() == 0  # ciclo novo ainda em dia
        set_mileage(vehicle, 59_800)
        with django_capture_on_commit_callbacks(execute=True):
            assert send_due_reminders() == 1

        titles = [title for title, *_ in notifications(client_account)]
        assert titles == ["Manutenção próxima", "Manutenção próxima"]
        assert (
            "faltam 400 km (prevista aos 60.200 km)"
            in notifications(client_account)[1][1]
        )

    def test_already_overdue_sends_overdue_message(
        self, client_account, django_capture_on_commit_callbacks
    ):
        vehicle = VehicleFactory(client=client_account, mileage_km=52_000)
        record = manual(
            vehicle, "Pastilhas de freio", km=40_000, interval=10_000, days_ago=400
        )

        with django_capture_on_commit_callbacks(execute=True):
            send_due_reminders()

        [(title, message, _)] = notifications(client_account)
        assert title == "Manutenção vencida"
        assert "passou 2.000 km da quilometragem prevista (50.000 km)" in message
        assert (
            MaintenanceReminder.objects.get(register_maintenance=record).status_reminder
            == "overdue"
        )

    def test_items_in_order_and_inactive_clients_get_nothing(
        self, django_capture_on_commit_callbacks
    ):
        in_order = VehicleFactory(mileage_km=42_000)
        manual(in_order, km=40_000, interval=10_000)
        for status in ("blocked", "inactive"):
            vehicle = VehicleFactory(
                client=ClientFactory(status=status), mileage_km=49_900
            )
            manual(vehicle, km=40_000, interval=10_000)

        with django_capture_on_commit_callbacks(execute=True):
            assert send_due_reminders() == 0

        assert not Notification.objects.exists()
        assert not MaintenanceReminder.objects.exists()

    def test_one_shot_expiration_job_does_not_send_reminders(self, client_account):
        vehicle = VehicleFactory(client=client_account, mileage_km=49_500)
        manual(vehicle, km=40_000, interval=10_000)

        call_command("run_expiration_jobs", stdout=StringIO())

        assert not MaintenanceReminder.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_runs_notify_once():
    vehicle = VehicleFactory(mileage_km=49_500)
    manual(vehicle, km=40_000, interval=10_000)
    barrier = threading.Barrier(2)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            results.append(send_due_reminders())
        except Exception as exc:  # noqa: BLE001 — o teste inspeciona
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors and sorted(results) == [0, 1]
    assert Notification.objects.filter(client=vehicle.client).count() == 1
    assert MaintenanceReminder.objects.count() == 1


# ------------------------------------------------- agendamento no serviço jobs


class _StopAfter:
    """Substitui `threading.Event` no loop: para depois de N esperas, sem dormir."""

    calls = 3

    def __init__(self):
        self.waits = 0

    def is_set(self):
        return self.waits >= self.calls

    def set(self):
        self.waits = self.calls

    def wait(self, timeout):
        self.waits += 1


@pytest.mark.parametrize(("reminders_interval", "expected"), [(3600, 1), (0, 0)])
def test_jobs_loop_sends_reminders_on_their_own_cadence(
    monkeypatch, reminders_interval, expected
):
    module = "apps.core.management.commands.run_expiration_jobs"
    sent = []
    monkeypatch.setattr(f"{module}.threading.Event", _StopAfter)
    monkeypatch.setattr(f"{module}.run_once", lambda: (0, 0, 0, 0, 0))
    monkeypatch.setattr(
        "apps.vehicles.reminders.send_due_reminders", lambda: sent.append(1) or 1
    )
    # Sem banco neste teste: o batimento (BE-092) é provado em apps/core/tests/test_heartbeat.py.
    monkeypatch.setattr(
        "apps.core.heartbeat.record_success", lambda *args, **kwargs: None
    )

    out = StringIO()
    call_command(
        "run_expiration_jobs",
        "--loop",
        "--interval",
        "1",
        "--reminders-interval",
        str(reminders_interval),
        stdout=out,
    )

    assert out.getvalue().count("orçamentos expirados") == 3  # 3 voltas do loop
    assert len(sent) == expected  # lembretes no máximo 1 vez por hora


def test_negative_reminders_interval_is_rejected():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="reminders-interval"):
        call_command("run_expiration_jobs", "--loop", "--reminders-interval", "-1")


@pytest.mark.django_db
def test_reminder_table_is_unique_per_execution():
    """A garantia de "não repetir" está no banco (`UNIQUE id_register_maintenance`)."""
    from django.db import IntegrityError, transaction

    record = manual(VehicleFactory(), km=40_000, interval=10_000)
    MaintenanceReminder.objects.create(
        register_maintenance=record, due_mileage_km=50_000, status_reminder="soon"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenanceReminder.objects.create(
            register_maintenance=record,
            due_mileage_km=50_000,
            status_reminder="overdue",
        )
