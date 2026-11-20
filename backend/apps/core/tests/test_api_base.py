"""P-13 / BE-016: base da API — paginação, serializador base e filtros por vírgula."""

import django_filters
import pytest
from apps.core.filters import CommaSeparatedChoiceFilter, CommaSeparatedFilter
from apps.core.serializers import SamModelSerializer
from apps.core.tests.factories import (
    AttendanceFactory,
    VehicleFactory,
    deliver_attendance,
    make_review,
)
from apps.reviews.models import Review
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


class TestSamPagination:
    URL = "/api/services/"  # catálogo semeado: 62 serviços

    def test_envelope_and_relative_links(self, api_client):
        first = api_client.get(self.URL).json()
        assert set(first) == {"count", "next", "previous", "results"}
        assert first["count"] == 62 and len(first["results"]) == 20
        assert first["next"] == "/api/services/?page=2" and first["previous"] is None

        second = api_client.get(first["next"]).json()
        assert (
            second["previous"] == "/api/services/"
            and second["next"] == "/api/services/?page=3"
        )

    def test_page_size_is_capped_at_100(self, api_client):
        body = api_client.get(self.URL, {"page_size": 1000}).json()
        assert len(body["results"]) == 62 and body["next"] is None
        assert len(api_client.get(self.URL, {"page_size": 5}).json()["results"]) == 5

    def test_page_out_of_range_is_404(self, api_client):
        assert api_client.get(self.URL, {"page": 99}).status_code == 404


class _VehicleOut(SamModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["plate"]


class _ReviewOut(SamModelSerializer):
    class Meta:
        model = Review
        fields = ["rating"]


def test_model_serializer_always_emits_id_first():
    vehicle = VehicleFactory()
    assert list(_VehicleOut(vehicle).data) == ["id", "plate"]
    assert _VehicleOut(vehicle).data["id"] == vehicle.pk

    budget, *_ = deliver_attendance(AttendanceFactory())
    review = make_review(budget)
    assert _ReviewOut(review).data["id"] == str(review.pk)  # UUID vira texto


class _VehicleFilter(django_filters.FilterSet):
    plate = CommaSeparatedFilter(field_name="plate")
    fuel = CommaSeparatedChoiceFilter(
        field_name="fuel", choices=[("flex", "Flex"), ("diesel", "Diesel")]
    )

    class Meta:
        model = Vehicle
        fields = []


def test_comma_separated_filters():
    a, b, _ = (
        VehicleFactory(fuel="flex"),
        VehicleFactory(fuel="diesel"),
        VehicleFactory(fuel="flex"),
    )
    queryset = Vehicle.objects.all()

    by_plate = _VehicleFilter({"plate": f"{a.plate},{b.plate}"}, queryset=queryset).qs
    assert set(by_plate) == {a, b}

    by_fuel = _VehicleFilter({"fuel": "diesel"}, queryset=queryset).qs
    assert list(by_fuel) == [b]

    invalid = _VehicleFilter({"fuel": "flex,gasolina"}, queryset=queryset)
    assert not invalid.is_valid() and "fuel" in invalid.errors
