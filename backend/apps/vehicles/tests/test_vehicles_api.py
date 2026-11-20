"""BE-043 (veículos), BE-044 (histórico) e BE-056 (histórico para a oficina)."""

from datetime import timedelta

import pytest
from apps.core.tests.factories import (
    AttendanceFactory,
    ClientFactory,
    RegisterMaintenanceFactory,
    VehicleFactory,
    deliver_attendance,
    fake_image_upload,
    jpeg_upload,
    make_ready_workshop,
    stored_name,
)
from apps.vehicles.models import RegisterMaintenance, Vehicle
from django.core.files.storage import default_storage
from django.utils import timezone

URL = "/api/vehicles/"


def payload(**overrides):
    data = {
        "brand": "Fiat",
        "model": "Argo",
        "year_fabrication": 2020,
        "year_model": 2021,
        "plate": "abc-1d23",
        "fuel": "flex",
        "exchange": "manual",
        "mileage_km": 30000,
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ BE-043


@pytest.mark.django_db
class TestVehicleCrud:
    def test_create_multipart_with_photos_by_position(
        self, client_session, client_account
    ):
        response = client_session.post(
            URL,
            payload(
                photo_1=jpeg_upload(),
                photo_3=jpeg_upload(),
                color="",
                information="Revisado",
                id_client=999,
            ),
            format="multipart",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["plate"] == "ABC1D23"
        assert body["photo_1"].startswith("http://testserver/media/vehicles/")
        assert body["photo_2"] is None
        assert body["photo_3"].startswith("http://testserver/media/vehicles/")
        assert body["color"] is None
        assert body["history_shared"] is False
        assert Vehicle.objects.get(pk=body["id"]).client_id == client_account.pk

    def test_duplicate_plate_same_client_is_400_but_other_client_is_ok(
        self, client_session, account_session
    ):
        assert client_session.post(URL, payload(), format="json").status_code == 201

        duplicate = client_session.post(URL, payload(plate="ABC1D23"), format="json")
        other = account_session(ClientFactory(), "client").post(
            URL, payload(), format="json"
        )

        assert duplicate.status_code == 400
        assert duplicate.json() == {"plate": ["Já existe um veículo com esta placa."]}
        assert other.status_code == 201

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("plate", "AB12345"),
            ("year_fabrication", 1899),
            ("year_model", timezone.now().year + 2),
            ("fuel", "querosene"),
            ("exchange", "pedal"),
            ("color", "x" * 21),
            ("information", "x" * 601),
            ("mileage_km", -1),
        ],
    )
    def test_invalid_field_is_400(self, client_session, field, value):
        response = client_session.post(URL, payload(**{field: value}), format="json")
        assert response.status_code == 400
        assert field in response.json()

    def test_mileage_is_required_on_create(self, client_session):
        data = payload()
        del data["mileage_km"]
        response = client_session.post(URL, data, format="json")
        assert response.status_code == 400
        assert "mileage_km" in response.json()

    def test_non_image_photo_is_400(self, client_session):
        response = client_session.post(
            URL, payload(photo_2=fake_image_upload()), format="multipart"
        )
        assert response.status_code == 400
        assert "photo_2" in response.json()
        assert not Vehicle.objects.exists()

    def test_list_and_detail_are_isolated(self, client_session, client_account):
        mine = VehicleFactory(client=client_account)
        other = VehicleFactory()

        body = client_session.get(URL).json()

        assert [row["id"] for row in body["results"]] == [mine.pk]
        assert client_session.get(f"{URL}{mine.pk}/").status_code == 200
        assert client_session.get(f"{URL}{other.pk}/").status_code == 404
        assert (
            client_session.patch(
                f"{URL}{other.pk}/", {"model": "X"}, format="json"
            ).status_code
            == 404
        )
        assert client_session.delete(f"{URL}{other.pk}/").status_code == 404

    def test_patch_history_shared_is_persisted(self, client_session, client_account):
        vehicle = VehicleFactory(client=client_account)

        response = client_session.patch(
            f"{URL}{vehicle.pk}/", {"history_shared": True}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["history_shared"] is True
        vehicle.refresh_from_db()
        assert vehicle.history_shared is True

    def test_patch_clears_only_one_photo_position(
        self, client_session, client_account, django_capture_on_commit_callbacks
    ):
        vehicle = VehicleFactory(client=client_account)
        url = f"{URL}{vehicle.pk}/"
        with django_capture_on_commit_callbacks(execute=True):
            body = client_session.patch(
                url,
                {"photo_1": jpeg_upload(), "photo_2": jpeg_upload()},
                format="multipart",
            ).json()
        first, second = stored_name(body["photo_1"]), stored_name(body["photo_2"])

        with django_capture_on_commit_callbacks(execute=True):
            body = client_session.patch(
                url, {"photo_2": "", "mileage_km": 51000}, format="multipart"
            ).json()

        assert stored_name(body["photo_1"]) == first
        assert body["photo_2"] is None
        assert body["mileage_km"] == 51000
        assert body["history_shared"] is False  # ausente na edição parcial: não muda
        assert default_storage.exists(first)
        assert not default_storage.exists(second)

    def test_patch_to_plate_of_another_own_vehicle_is_400(
        self, client_session, client_account
    ):
        VehicleFactory(client=client_account, plate="AAA1111")
        vehicle = VehicleFactory(client=client_account, plate="BBB2222")
        response = client_session.patch(
            f"{URL}{vehicle.pk}/", {"plate": "aaa-1111"}, format="json"
        )
        assert response.status_code == 400
        assert "plate" in response.json()
        assert (
            client_session.patch(
                f"{URL}{vehicle.pk}/", {"plate": "bbb2222"}, format="json"
            ).status_code
            == 200
        )

    def test_delete_vehicle_without_records(
        self, client_session, client_account, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            body = client_session.post(
                URL, payload(photo_1=jpeg_upload()), format="multipart"
            ).json()
        photo = stored_name(body["photo_1"])

        with django_capture_on_commit_callbacks(execute=True):
            response = client_session.delete(f"{URL}{body['id']}/")

        assert response.status_code == 204
        assert not Vehicle.objects.filter(pk=body["id"]).exists()
        assert not default_storage.exists(photo)

    @pytest.mark.parametrize("dependency", ["attendance", "history"])
    def test_delete_vehicle_in_use_is_409(
        self, client_session, client_account, dependency
    ):
        vehicle = VehicleFactory(client=client_account)
        if dependency == "attendance":
            AttendanceFactory(client=client_account, vehicle=vehicle)
        else:
            RegisterMaintenanceFactory(vehicle=vehicle)

        response = client_session.delete(f"{URL}{vehicle.pk}/")

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Veículos com atendimentos ou histórico não podem ser excluídos."
        }
        assert Vehicle.objects.filter(pk=vehicle.pk).exists()

    def test_access_matrix(self, api_client, workshop_session):
        assert api_client.get(URL).status_code == 401
        assert workshop_session.get(URL).status_code == 403
        assert workshop_session.post(URL, payload(), format="json").status_code == 403


# ------------------------------------------------------------------ BE-044


@pytest.mark.django_db
class TestVehicleHistory:
    def history_url(self, vehicle):
        return f"{URL}{vehicle.pk}/history/"

    def test_manual_record_appears_as_service_without_workshop(
        self, client_session, client_account
    ):
        vehicle = VehicleFactory(client=client_account, mileage_km=50000)
        today = timezone.localdate().isoformat()

        response = client_session.post(
            self.history_url(vehicle),
            {
                "service_name": "  Troca   de óleo ",
                "date_maintenance": today,
                "mileage_km": 52000,
                "observations": "",
            },
            format="json",
        )

        assert response.status_code == 201, response.json()
        record = response.json()
        assert (
            record["record_type"],
            record["description"],
            record["id_workshop"],
        ) == ("service", "Troca de óleo", None)
        assert record["id"] == f"service-{record['id_record']}"
        rows = client_session.get(self.history_url(vehicle)).json()["results"]
        assert [row["id"] for row in rows] == [record["id"]]
        vehicle.refresh_from_db()
        assert vehicle.mileage_km == 52000

    def test_lower_mileage_does_not_reduce_vehicle(
        self, client_session, client_account
    ):
        vehicle = VehicleFactory(client=client_account, mileage_km=50000)
        client_session.post(
            self.history_url(vehicle),
            {
                "service_name": "Alinhamento",
                "date_maintenance": "2020-01-10",
                "mileage_km": 20000,
            },
            format="json",
        )
        vehicle.refresh_from_db()
        assert vehicle.mileage_km == 50000

    def test_today_at_noon_is_not_future_but_tomorrow_is(
        self, client_session, client_account
    ):
        vehicle = VehicleFactory(client=client_account)
        today_noon = timezone.localtime().replace(hour=12, minute=0).isoformat()
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

        ok = client_session.post(
            self.history_url(vehicle),
            {"service_name": "A", "date_maintenance": today_noon},
            format="json",
        )
        future = client_session.post(
            self.history_url(vehicle),
            {"service_name": "B", "date_maintenance": tomorrow},
            format="json",
        )

        assert ok.status_code == 201
        assert future.status_code == 400
        assert "date_maintenance" in future.json()

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({"service_name": "", "date_maintenance": "2024-01-01"}, "service_name"),
            (
                {"service_name": "x" * 256, "date_maintenance": "2024-01-01"},
                "service_name",
            ),
            ({"service_name": "A"}, "date_maintenance"),
            (
                {
                    "service_name": "A",
                    "date_maintenance": "2024-01-01",
                    "id_service": 999999,
                },
                "id_service",
            ),
            (
                {
                    "service_name": "A",
                    "date_maintenance": "2024-01-01",
                    "mileage_km": -5,
                },
                "mileage_km",
            ),
        ],
    )
    def test_invalid_manual_record_is_400(
        self, client_session, client_account, body, field
    ):
        vehicle = VehicleFactory(client=client_account)
        response = client_session.post(self.history_url(vehicle), body, format="json")
        assert response.status_code == 400
        assert field in response.json()

    def test_delivered_attendance_lists_executed_services_and_parts_only(
        self, client_session, client_account
    ):
        attendance = AttendanceFactory(
            client=client_account, workshop=make_ready_workshop()
        )
        budget, service_item, part_item = deliver_attendance(attendance)

        rows = client_session.get(self.history_url(attendance.vehicle)).json()[
            "results"
        ]

        assert sorted((row["record_type"], row["description"]) for row in rows) == [
            ("part", "Filtro"),
            ("service", "Troca de óleo"),
        ]
        part = next(row for row in rows if row["record_type"] == "part")
        assert (part["quantity"], part["unit_price"], part["id_workshop"]) == (
            "2.000",
            "30.00",
            attendance.workshop_id,
        )
        assert part["workshop_name"] == attendance.workshop.name_fantasy

    def test_history_is_append_only(self, client_session, client_account):
        record = RegisterMaintenanceFactory(
            vehicle=VehicleFactory(client=client_account)
        )
        vehicle_url = self.history_url(record.vehicle)
        record_url = f"{vehicle_url}service-{record.pk}/"

        assert client_session.get(record_url).status_code == 200
        assert (
            client_session.patch(
                record_url, {"service_name": "X"}, format="json"
            ).status_code
            == 405
        )
        assert (
            client_session.put(
                record_url, {"service_name": "X"}, format="json"
            ).status_code
            == 405
        )
        assert client_session.delete(record_url).status_code == 405
        assert client_session.delete(vehicle_url).status_code == 405
        assert (
            RegisterMaintenance.objects.get(pk=record.pk).service_name
            == "Troca de óleo"
        )

    def test_other_client_vehicle_history_is_404(self, client_session):
        record = RegisterMaintenanceFactory()
        url = self.history_url(record.vehicle)
        assert client_session.get(url).status_code == 404
        assert (
            client_session.post(
                url,
                {"service_name": "A", "date_maintenance": "2024-01-01"},
                format="json",
            ).status_code
            == 404
        )
        assert client_session.get(f"{url}service-{record.pk}/").status_code == 404


# ------------------------------------------------------------------ BE-056


@pytest.mark.django_db
class TestWorkshopVehicleHistory:
    def test_three_combinations(self, ready_workshop, ready_workshop_session):
        linked = AttendanceFactory(workshop=ready_workshop).vehicle
        RegisterMaintenanceFactory(vehicle=linked)
        unlinked = VehicleFactory(history_shared=True)
        url = "/api/workshop/vehicles/{}/history/"

        not_shared = ready_workshop_session.get(url.format(linked.pk))
        assert not_shared.status_code == 403
        assert not_shared.json() == {
            "detail": "O cliente não autorizou a consulta do histórico deste veículo."
        }

        Vehicle.objects.filter(pk=linked.pk).update(history_shared=True)
        shared = ready_workshop_session.get(url.format(linked.pk))
        assert shared.status_code == 200
        assert shared.json()["count"] == 1
        assert set(shared.json()["results"][0]) >= {
            "record_type",
            "description",
            "date_maintenance",
            "mileage_km",
        }

        assert ready_workshop_session.get(url.format(unlinked.pk)).status_code == 404

    def test_access_matrix(self, api_client, client_session, workshop_session):
        url = f"/api/workshop/vehicles/{VehicleFactory().pk}/history/"
        assert api_client.get(url).status_code == 401
        assert client_session.get(url).status_code == 403
        assert workshop_session.get(url).status_code == 403  # cadastro não concluído
