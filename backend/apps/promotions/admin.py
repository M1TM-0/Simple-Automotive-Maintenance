"""Divulgações pagas no Django Admin: confirmação manual do pagamento (BE-076, DP-09).

Sem gateway: o admin confere o recebimento por fora e usa as ações abaixo. Os
campos são só leitura — a divulgação nasce pela oficina (BE-064) e muda de estado
só pelas ações, que passam pelos serviços (`apps/promotions/services.py`) e
pelas triggers do banco. Cada ação vai para o log de auditoria `sam.audit` e para
o histórico do Django Admin.

- **Confirmar pagamento**: `pending|failed → paid`; se o período já começou, a
  divulgação entra no ar na hora; senão a rotina `jobs` a ativa no início.
- **Pagamento não identificado**: `pending → failed` (pode ser confirmado depois).
- **Cancelar divulgação**: tira do ar; se estava paga, o pagamento vira
  `refunded` (estorno a fazer pelo admin).
"""

from apps.core.exceptions import ApiConflict
from apps.moderation.audit import log_admin_action
from apps.promotions import services
from apps.promotions.models import PromotionAdvertisement
from django.contrib import admin, messages


@admin.register(PromotionAdvertisement)
class PromotionAdvertisementAdmin(admin.ModelAdmin):
    list_display = (
        "id_promotion_advertisement",
        "promotion",
        "workshop",
        "date_start",
        "date_end",
        "advertising_price",
        "payment_status",
        "status_advertisement",
    )
    list_filter = ("payment_status", "status_advertisement")
    list_select_related = ("promotion__workshop",)
    search_fields = ("promotion__title", "promotion__workshop__name_fantasy")
    ordering = ("-date_creation",)
    readonly_fields = (
        "promotion",
        "workshop",
        "image_url",
        "date_creation",
        "date_start",
        "date_end",
        "advertising_price",
        "payment_status",
        "status_advertisement",
    )
    fields = readonly_fields
    actions = ("confirm_payment", "mark_payment_failed", "cancel_advertisements")

    @admin.display(description="Oficina")
    def workshop(self, obj):
        return obj.promotion.workshop.name_fantasy

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _apply(self, request, queryset, action, operation, done):
        changed = 0
        for advertisement_id in queryset.values_list("pk", flat=True):
            try:
                result = operation(advertisement_id)
            except ApiConflict as exc:
                self.message_user(
                    request,
                    f"Divulgação #{advertisement_id}: {exc.detail}",
                    messages.WARNING,
                )
                continue
            if result is False:
                continue
            changed += 1
            advertisement = PromotionAdvertisement.objects.get(pk=advertisement_id)
            log_admin_action(
                request,
                f"advertisement.{action}",
                target_type="advertisement",
                target_id=str(advertisement_id),
                payment_status=advertisement.payment_status,
                status_advertisement=advertisement.status_advertisement,
            )
            self.log_change(request, advertisement, done)
        self.message_user(
            request, f"{changed} divulgação(ões): {done.lower()}", messages.SUCCESS
        )

    @admin.action(description="Confirmar pagamento (entra no ar no início do período)")
    def confirm_payment(self, request, queryset):
        self._apply(
            request,
            queryset,
            "confirm_payment",
            services.confirm_advertisement_payment,
            "Pagamento confirmado.",
        )

    @admin.action(description="Marcar pagamento como não identificado")
    def mark_payment_failed(self, request, queryset):
        self._apply(
            request,
            queryset,
            "payment_failed",
            services.mark_advertisement_payment_failed,
            "Pagamento marcado como não identificado.",
        )

    @admin.action(description="Cancelar divulgação (estorno se paga)")
    def cancel_advertisements(self, request, queryset):
        self._apply(
            request,
            queryset,
            "cancel",
            services.cancel_advertisement,
            "Divulgação cancelada.",
        )
