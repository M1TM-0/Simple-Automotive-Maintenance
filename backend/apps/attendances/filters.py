from apps.attendances.models import Attendance, AttendanceStatus
from apps.core.filters import CommaSeparatedChoiceFilter
from django_filters import rest_framework as filters


class ClientAttendanceFilter(filters.FilterSet):
    """`?status=a,b,c` (RI-15) e `?vehicle=<id>`."""

    status = CommaSeparatedChoiceFilter(
        field_name="status_attendance", choices=AttendanceStatus.choices
    )
    vehicle = filters.NumberFilter(field_name="vehicle_id")

    class Meta:
        model = Attendance
        fields = []


class WorkshopAttendanceFilter(filters.FilterSet):
    status = CommaSeparatedChoiceFilter(
        field_name="status_attendance", choices=AttendanceStatus.choices
    )

    class Meta:
        model = Attendance
        fields = []
