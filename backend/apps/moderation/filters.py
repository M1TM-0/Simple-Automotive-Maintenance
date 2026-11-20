from apps.catalog.models import SolicitationStatus, WorkshopService
from apps.core.filters import CommaSeparatedChoiceFilter
from apps.reviews.models import Denunciation, DenunciationStatus
from django_filters import rest_framework as filters

TARGET_FIELDS = {
    "review": "review_id",
    "promotion": "promotion_id",
    "advertisement": "advertisement_id",
}


class DenunciationFilter(filters.FilterSet):
    """`?status=pending,in_review` e `?target_type=review|promotion|advertisement`."""

    status = CommaSeparatedChoiceFilter(
        field_name="status_denunciation", choices=DenunciationStatus.choices
    )
    target_type = filters.ChoiceFilter(
        choices=[(key, key) for key in TARGET_FIELDS], method="filter_target_type"
    )

    class Meta:
        model = Denunciation
        fields = []

    def filter_target_type(self, queryset, name, value):
        return queryset.filter(**{f"{TARGET_FIELDS[value]}__isnull": False})


class ServiceRequestFilter(filters.FilterSet):
    """`?status=pending,approved,rejected`; sem o parâmetro, só as pendentes (a fila)."""

    status = CommaSeparatedChoiceFilter(
        field_name="status_solicitation", choices=SolicitationStatus.choices
    )

    class Meta:
        model = WorkshopService
        fields = []

    def filter_queryset(self, queryset):
        if not self.form.cleaned_data.get("status"):
            queryset = queryset.filter(status_solicitation=SolicitationStatus.PENDING)
        return super().filter_queryset(queryset)
