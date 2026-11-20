"""Curadoria do catálogo global no Django Admin (BE-075, DP-03).

Categorias e serviços globais podem ser criados e editados; não excluídos
(serviços e solicitações apontam para eles — desative o serviço com `active`).
O nome do serviço é gravado "limpo" e único pelo nome normalizado, as mesmas
regras do banco (`ck_service_name_clean`, `uq_service_name_normalized`),
validadas no formulário para virar mensagem e não erro 500. Solicitações de
serviço personalizado são decididas pela API (`/api/admin/service-requests/`, BE-074).
"""

from apps.catalog.models import Service, ServiceCategory
from apps.core.validators import clean_service_name
from django import forms
from django.contrib import admin
from django.db.models import F, Func, Value


class ServiceAdminForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ("name", "description", "category", "active")

    def clean_name(self):
        name = clean_service_name(self.cleaned_data["name"] or "")
        if not name:
            raise forms.ValidationError("Informe o nome do serviço.")
        duplicates = (
            Service.objects.annotate(
                key=Func(F("name"), function="normalize_service_name")
            )
            .filter(key=Func(Value(name), function="normalize_service_name"))
            .exclude(pk=self.instance.pk)
        )
        if duplicates.exists():
            raise forms.ValidationError(
                "Já existe um serviço com este nome no catálogo."
            )
        return name


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("id_service_category", "name")
    search_fields = ("name",)
    fields = ("name", "description")
    ordering = ("name",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    form = ServiceAdminForm
    list_display = ("id_service", "name", "category", "active")
    list_filter = ("active", "category")
    list_select_related = ("category",)
    search_fields = ("name",)
    ordering = ("name",)

    def has_delete_permission(self, request, obj=None):
        return False
