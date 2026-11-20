import pytest
from apps.attendances.models import Budget, BudgetItem
from apps.core.tests import factories as f
from apps.core.tests.factories import deliver_attendance, make_review
from apps.vehicles.models import (
    RegisterMaintenance,
    RegisterMaintenancePart,
    VehicleMaintenanceHistory,
)
from django.apps import apps
from django.db import IntegrityError, connection, transaction

SAM_APPS = {
    "accounts",
    "attendances",
    "catalog",
    "chat",
    "notifications",
    "promotions",
    "reviews",
    "vehicles",
    "workshops",
}


def sam_models():
    return [m for m in apps.get_models() if m._meta.app_label in SAM_APPS]


def scalar(sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_migrated_schema_has_expected_objects():
    assert (
        scalar(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public' "
            "AND tablename NOT LIKE 'django\\_%' AND tablename NOT LIKE 'auth\\_%'"
        )
        == 25
    )  # 23 do init.sql + MAINTENANCE_REMINDER (BE-077) + JOB_HEARTBEAT (core/0003)
    assert scalar("SELECT count(*) FROM pg_views WHERE schemaname='public'") == 3
    assert (
        scalar(
            "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace"
        )
        == 16
    )
    assert (
        scalar(
            "SELECT count(*) FROM pg_proc WHERE pronamespace = 'public'::regnamespace"
        )
        == 26
    )
    assert scalar("SELECT count(*) FROM service") == 62
    assert scalar("SELECT count(*) FROM service_category") == 11


@pytest.mark.django_db
@pytest.mark.parametrize("model", sam_models(), ids=lambda m: m._meta.db_table)
def test_model_columns_match_database(model):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            [model._meta.db_table],
        )
        db_columns = {row[0] for row in cursor.fetchall()}

    model_columns = {field.column for field in model._meta.concrete_fields}

    assert model_columns == db_columns


@pytest.mark.django_db
def test_every_unmanaged_model_is_registered():
    assert (
        len(sam_models()) == 27
    )  # 23 tabelas do init.sql + 3 views + MaintenanceReminder
    assert all(not m._meta.managed for m in sam_models())


@pytest.mark.django_db
def test_budget_item_generated_columns_are_returned_after_create():
    item = f.BudgetItemFactory(quantity="2.5", unit_price="10.01")

    assert str(item.subtotal) == "25.03"
    assert item.service_item_type is None


@pytest.mark.django_db
def test_budget_total_is_maintained_by_trigger_and_manual_write_is_rejected():
    budget = f.BudgetFactory()
    f.BudgetItemFactory(budget=budget, unit_price="100.00")
    f.BudgetItemFactory(budget=budget, quantity="2", unit_price="30.00")
    budget.refresh_from_db()
    assert str(budget.total_price) == "160.00"

    budget.total_price = 1
    with pytest.raises(IntegrityError), transaction.atomic():
        budget.save(update_fields=["total_price"])


@pytest.mark.django_db
def test_budget_defaults_come_from_database():
    budget = f.BudgetFactory()
    budget.refresh_from_db()

    assert budget.status_budget == "pending"
    assert budget.total_price == 0
    assert 6.9 < (budget.date_validity - budget.date_creation).days + 1 <= 8


@pytest.mark.django_db
def test_defaults_for_status_and_dates_come_from_database():
    client = f.ClientFactory()
    workshop = f.WorkshopFactory()
    page = f.PagWorkshopFactory(workshop=workshop)
    attendance = f.AttendanceFactory()
    for obj in (client, workshop, page, attendance):
        obj.refresh_from_db()

    assert client.status == "active" and client.created_at
    assert workshop.status == "active"
    assert page.photo_profile == "default-profile.png"
    assert attendance.status_attendance == "requested"


@pytest.mark.django_db
def test_delivery_generates_history_and_view_is_readable():
    attendance = f.AttendanceFactory()
    budget, service_item, part_item = deliver_attendance(attendance)

    assert RegisterMaintenance.objects.filter(budget_item=service_item).exists()
    part = RegisterMaintenancePart.objects.get(budget_item=part_item)
    assert part.item_type == "product" and part.item_execution_status == "executed"

    rows = VehicleMaintenanceHistory.objects.filter(
        id_vehicle=attendance.vehicle_id
    ).order_by("record_type")
    assert [r.record_type for r in rows] == ["part", "service"]
    assert rows[1].interval_km is None


@pytest.mark.django_db
def test_review_requires_delivery_and_is_unique():
    attendance = f.AttendanceFactory()
    budget, *_ = deliver_attendance(attendance)

    review = make_review(budget)
    review.refresh_from_db()
    assert review.status_review == "published"

    with pytest.raises(IntegrityError), transaction.atomic():
        make_review(budget)


@pytest.mark.django_db
def test_vehicle_mileage_and_history_columns():
    vehicle = f.VehicleFactory(mileage_km=1000)
    vehicle.history_shared = True
    vehicle.save(update_fields=["history_shared"])
    vehicle.refresh_from_db()
    assert vehicle.history_shared is True

    vehicle.mileage_km = -1
    with pytest.raises(IntegrityError), transaction.atomic():
        vehicle.save(update_fields=["mileage_km"])


@pytest.mark.django_db
def test_notification_url_constraint():
    f.NotificationFactory(url="attendance.html?id=12")

    with pytest.raises(IntegrityError), transaction.atomic():
        f.NotificationFactory(url="http://evil.com")


@pytest.mark.django_db
def test_maintenance_interval_is_exposed_in_history_view():
    maintenance = f.RegisterMaintenanceFactory(interval_km=10000)
    row = VehicleMaintenanceHistory.objects.get(id_vehicle=maintenance.vehicle_id)
    assert row.interval_km == 10000

    maintenance.interval_km = 0
    with pytest.raises(IntegrityError), transaction.atomic():
        maintenance.save(update_fields=["interval_km"])


@pytest.mark.django_db
def test_attendance_technical_notes_do_not_touch_observations():
    attendance = f.AttendanceFactory(observations="Pedido do cliente")
    attendance.technical_notes = "Folga na suspensão"
    attendance.save(update_fields=["technical_notes"])
    attendance.refresh_from_db()
    assert attendance.observations == "Pedido do cliente"


@pytest.mark.django_db
def test_perf_indexes_exist():
    assert (
        scalar(
            "SELECT count(*) FROM pg_indexes WHERE indexname IN "
            "('idx_budget_workshop', 'idx_message_unread')"
        )
        == 2
    )


@pytest.mark.django_db
def test_promotion_views_expose_effective_status():
    promotion = f.PromotionFactory()
    advertisement = f.PromotionAdvertisementFactory(promotion=promotion)

    from apps.promotions.models import AdvertisementEffective, PromotionEffective

    effective = PromotionEffective.objects.get(pk=promotion.pk)
    assert effective.effective_status == "active" and effective.is_valid_now
    assert (
        AdvertisementEffective.objects.get(pk=advertisement.pk).is_running_now is False
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "factory",
    [
        f.ClientFactory,
        f.WorkshopFactory,
        f.PagWorkshopFactory,
        f.PointOfInterestFactory,
        f.OperationHourFactory,
        f.VehicleFactory,
        f.ServiceCategoryFactory,
        f.ServiceFactory,
        f.WorkshopServiceFactory,
        f.ProductFactory,
        f.AttendanceFactory,
        f.BudgetFactory,
        f.BudgetItemFactory,
        f.RegisterMaintenanceFactory,
        f.ChatFactory,
        f.MessageFactory,
        f.FavoriteFactory,
        f.NotificationFactory,
        f.PromotionFactory,
        f.PromotionAdvertisementFactory,
        f.DenunciationFactory,
    ],
    ids=lambda fac: fac._meta.model._meta.db_table,
)
def test_round_trip_create_read_update(factory):
    instance = factory()
    model = type(instance)

    assert model.objects.get(pk=instance.pk).pk == instance.pk

    instance.refresh_from_db()
    instance.save()
    assert model.objects.filter(pk=instance.pk).count() == 1


@pytest.mark.django_db
def test_deleting_owner_cascades_where_database_says_so():
    chat = f.ChatFactory()
    f.MessageFactory(chat=chat)
    f.FavoriteFactory(client=chat.client)

    chat.client.delete()

    from apps.chat.models import Chat, Message

    assert not Chat.objects.filter(pk=chat.pk).exists()
    assert not Message.objects.filter(chat_id=chat.pk).exists()


@pytest.mark.django_db
def test_budget_item_model_is_importable_for_services():
    assert BudgetItem.objects.count() == 0 and Budget.objects.count() == 0
