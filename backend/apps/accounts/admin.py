"""Django Admin de contas (BE-075, RF-S07) e anonimização (BE-078, DP-18).

Admin provisório da DP-03 (só `is_staff`, em `/admin/`, atrás de HTTPS em produção).
Regras:

- `password_hash` nunca aparece no formulário; e-mail, CNPJ e datas são só leitura.
- Sem incluir (contas nascem no cadastro, com senha) e sem excluir (RESTRICT
  preserva o histórico; DP-18 manda desativar/anonimizar).
- Salvar grava só os campos alterados (`update_fields`): o formulário não
  sobrescreve uma senha trocada enquanto ele estava aberto.
- Toda troca de status e toda anonimização vão para o log de auditoria
  `sam.audit` e para o histórico do próprio Django Admin (`LogEntry`).
"""

from apps.accounts import services
from apps.accounts.models import AccountStatus, Client, Workshop
from apps.core.exceptions import ApiConflict
from apps.moderation.audit import log_admin_action
from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse


class _AccountForm(forms.ModelForm):
    def clean_status(self):
        status = self.cleaned_data["status"]
        if (
            self.instance.pk
            and status == AccountStatus.ACTIVE
            and services.is_anonymized(self.instance)
        ):
            raise forms.ValidationError("Uma conta anonimizada não pode ser reativada.")
        return status


class _AccountAdmin(admin.ModelAdmin):
    role = None
    form = _AccountForm
    list_filter = ("status",)
    list_per_page = 50
    ordering = ("-created_at",)
    actions = (
        "block_accounts",
        "activate_accounts",
        "deactivate_accounts",
        "anonymize_accounts",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        fields = [name for name in form.changed_data if name != "status"]
        if fields:
            obj.save(update_fields=fields)
        if "status" in form.changed_data:
            self._change_status(
                request, obj.pk, form.cleaned_data["status"], log_entry=False
            )

    # ---------------------------------------------------------------- ações

    def _audit(self, request, account, action, **extra):
        log_admin_action(
            request,
            f"account.{action}",
            target_type=self.role,
            target_id=str(account.pk),
            **extra,
        )

    def _change_status(self, request, account_id, status, *, log_entry=True):
        account, previous = services.set_account_status(self.role, account_id, status)
        if previous == status:
            return False
        self._audit(request, account, "status", from_status=previous, to_status=status)
        if log_entry:  # o formulário já registra a própria alteração
            self.log_change(request, account, f"Status: {previous} → {status}.")
        return True

    def _bulk_status(self, request, queryset, status, done):
        changed = 0
        for account_id in queryset.values_list("pk", flat=True):
            try:
                changed += self._change_status(request, account_id, status)
            except ApiConflict as exc:
                self.message_user(
                    request, f"Conta #{account_id}: {exc.detail}", messages.WARNING
                )
        self.message_user(request, f"{changed} conta(s) {done}.", messages.SUCCESS)

    @admin.action(description="Bloquear contas selecionadas")
    def block_accounts(self, request, queryset):
        self._bulk_status(request, queryset, AccountStatus.BLOCKED, "bloqueada(s)")

    @admin.action(description="Ativar contas selecionadas")
    def activate_accounts(self, request, queryset):
        self._bulk_status(request, queryset, AccountStatus.ACTIVE, "ativada(s)")

    @admin.action(description="Desativar contas selecionadas (preserva o histórico)")
    def deactivate_accounts(self, request, queryset):
        self._bulk_status(request, queryset, AccountStatus.INACTIVE, "desativada(s)")

    @admin.action(description="Anonimizar dados pessoais (irreversível)")
    def anonymize_accounts(self, request, queryset):
        if request.POST.get("confirm") != "yes":
            return TemplateResponse(
                request,
                "admin/accounts/anonymize_confirmation.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Anonimizar dados pessoais",
                    "opts": self.model._meta,
                    "accounts": queryset,
                    "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                },
            )
        count = 0
        for account_id in queryset.values_list("pk", flat=True):
            account = services.anonymize_account(self.role, account_id)
            self._audit(request, account, "anonymize")
            self.log_change(request, account, "Dados pessoais anonimizados (DP-18).")
            count += 1
        self.message_user(
            request, f"{count} conta(s) anonimizada(s).", messages.SUCCESS
        )
        return None


@admin.register(Client)
class ClientAdmin(_AccountAdmin):
    role = "client"
    list_display = ("id_client", "name", "email", "status", "created_at")
    search_fields = ("name", "email")
    fields = ("name", "email", "phone_number", "status", "photo_profile", "created_at")
    readonly_fields = ("email", "photo_profile", "created_at")


@admin.register(Workshop)
class WorkshopAdmin(_AccountAdmin):
    role = "workshop"
    list_display = (
        "id_workshop",
        "name_fantasy",
        "cnpj",
        "email",
        "status",
        "created_at",
    )
    search_fields = ("name_fantasy", "name_responsible", "email", "cnpj")
    fields = (
        "name_fantasy",
        "name_responsible",
        "email",
        "cnpj",
        "phone_number",
        "status",
        "point_of_interest",
        "created_at",
    )
    readonly_fields = ("email", "cnpj", "point_of_interest", "created_at")
