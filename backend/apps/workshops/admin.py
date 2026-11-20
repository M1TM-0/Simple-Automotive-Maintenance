"""Pontos de interesse do mapa no Django Admin (BE-075).

A carga em lote é o `manage.py import_pois` (BE-071); aqui o admin corrige ou
inclui pontos avulsos. As regras do banco (coordenadas, origem externa completa e
única) são validadas no formulário. Excluir um ponto vinculado a uma oficina só
desfaz o vínculo (`ON DELETE SET NULL`).
"""

from apps.workshops.models import PointOfInterest
from django import forms
from django.contrib import admin


class PointOfInterestForm(forms.ModelForm):
    latitude = forms.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90
    )
    longitude = forms.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180
    )

    class Meta:
        model = PointOfInterest
        fields = (
            "name",
            "type",
            "latitude",
            "longitude",
            "address",
            "external_source",
            "external_id",
        )

    def clean(self):
        data = super().clean()
        source, external_id = (
            data.get("external_source") or None,
            data.get("external_id") or None,
        )
        data["external_source"], data["external_id"] = source, external_id
        if (source is None) != (external_id is None):
            raise forms.ValidationError(
                "Informe a origem externa e o identificador juntos (ou nenhum dos dois)."
            )
        if source and (
            PointOfInterest.objects.filter(
                external_source=source, external_id=external_id
            )
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "Este ponto de interesse já foi importado desta origem."
            )
        return data


@admin.register(PointOfInterest)
class PointOfInterestAdmin(admin.ModelAdmin):
    form = PointOfInterestForm
    list_display = (
        "id_point_of_interest",
        "name",
        "type",
        "latitude",
        "longitude",
        "external_source",
    )
    list_filter = ("type", "external_source")
    search_fields = ("name", "address")
    ordering = ("name",)
