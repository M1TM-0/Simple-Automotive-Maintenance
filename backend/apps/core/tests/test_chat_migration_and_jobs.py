from datetime import timedelta
from io import StringIO

import pytest
from apps.attendances.models import Budget
from apps.core.tests import factories as f
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_chat_migration_merges_duplicates_preserving_messages():
    executor = MigrationExecutor(connection)
    executor.migrate([("chat", "0001_initial")])

    client = f.ClientFactory()
    workshop = f.WorkshopFactory()
    first = f.ChatFactory(client=client, workshop=workshop)
    f.MessageFactory(chat=first, content="primeira")
    duplicate_id = None
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO chat (id_client, id_workshop, date_creation) "
            "VALUES (%s, %s, NOW() + interval '1 hour') RETURNING id_chat",
            [client.pk, workshop.pk],
        )
        duplicate_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO message (id_chat, id_client, content) VALUES (%s, %s, 'segunda')",
            [duplicate_id, client.pk],
        )

    executor = MigrationExecutor(connection)
    executor.migrate([("chat", "0002_chat_unique_pair")])

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM chat WHERE id_client=%s", [client.pk])
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT content FROM message WHERE id_chat=%s ORDER BY id_message",
            [first.pk],
        )
        assert [row[0] for row in cursor.fetchall()] == ["primeira", "segunda"]


@pytest.mark.django_db(transaction=True)
def test_migrations_are_reversible_and_reapplicable():
    targets = [
        ("core", "0001_init_schema"),
        ("vehicles", "0001_initial"),
        ("chat", "0001_initial"),
        ("notifications", "0001_initial"),
        ("attendances", "0001_initial"),
    ]
    executor = MigrationExecutor(connection)
    executor.migrate(targets)

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='vehicle' AND column_name IN ('mileage_km','history_shared')"
        )
        assert cursor.fetchone()[0] == 2


@pytest.mark.django_db
def test_expiration_job_expires_overdue_budget_and_is_idempotent():
    attendance = f.AttendanceFactory()
    now = timezone.now()
    budget = Budget.objects.create(
        attendance=attendance,
        workshop=attendance.workshop,
        date_creation=now - timedelta(days=2),
        date_validity=now - timedelta(days=1),
    )
    out = StringIO()
    call_command("run_expiration_jobs", stdout=out)

    budget.refresh_from_db()
    attendance.refresh_from_db()
    assert budget.status_budget == "expired"
    assert attendance.status_attendance == "requested"
    assert "orçamentos expirados: 1" in out.getvalue()

    out = StringIO()
    call_command("run_expiration_jobs", stdout=out)
    assert (
        "orçamentos expirados: 0 | promoções expiradas: 0 | divulgações concluídas: 0"
        in out.getvalue()
    )


@pytest.mark.django_db
def test_expiration_job_exits_with_error_when_database_fails(caplog):
    from unittest import mock

    with mock.patch(
        "apps.core.management.commands.run_expiration_jobs.run_once",
        side_effect=DatabaseError("down"),
    ):
        with pytest.raises(CommandError, match="Falha"):
            call_command("run_expiration_jobs")
