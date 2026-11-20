"""Casos de uso da oficina logada (BE-037…BE-040)."""

from apps.accounts.models import Workshop
from apps.core.db_errors import CHECK_VIOLATION, db_error_details
from apps.core.exceptions import ApiConflict, ApiValidationFailure
from apps.core.storage import apply_image_changes
from apps.core.transactions import transactional
from apps.workshops.models import OperationHour, PagWorkshop, PointOfInterest
from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound

MAX_OPERATION_HOURS = 50
POINT_TAKEN = "Este ponto do mapa já está vinculado a outra oficina."


def _lock_workshop(workshop_id: int) -> Workshop:
    return Workshop.objects.select_for_update().get(pk=workshop_id)


@transactional
def update_workshop_account(workshop_id: int, data: dict) -> Workshop:
    """`PATCH /workshop/me/` — nome fantasia, responsável e telefone (BE-037)."""
    workshop = _lock_workshop(workshop_id)
    fields = []
    for field in ("name_fantasy", "name_responsible"):
        if field in data:
            value = data[field].strip()
            if not value:
                raise ApiValidationFailure(
                    {field: ["Este campo não pode ficar em branco."]}
                )
            setattr(workshop, field, value)
            fields.append(field)
    if "phone_number" in data:
        workshop.phone_number = data["phone_number"]
        fields.append("phone_number")
    if fields:
        workshop.save(update_fields=fields)
    return workshop


@transactional
def update_workshop_page(workshop_id: int, data: dict) -> PagWorkshop:
    """`PATCH /workshop/page/` — descrição, foto de perfil e banner (BE-038).

    Arquivo novo substitui; `None` remove. O arquivo antigo só é apagado após o
    commit (`apply_image_changes`). Sem foto de perfil a página volta ao padrão
    do banco (`default-profile.png`); o banner fica nulo.
    """
    _lock_workshop(workshop_id)
    page, _ = PagWorkshop.objects.get_or_create(workshop_id=workshop_id)

    if "description" in data:
        page.description = data["description"]
        page.save(update_fields=["description"])

    if "photo_banner" in data:
        apply_image_changes(
            page, {"photo_banner": data["photo_banner"]}, folder="workshops/banners"
        )

    if "photo_profile" in data:
        photo = data["photo_profile"]
        apply_image_changes(page, {"photo_profile": photo}, folder="workshops/profiles")
        if photo is None:
            page.photo_profile = settings.SAM_DEFAULT_PROFILE_IMAGE
            page.save(update_fields=["photo_profile"])
    return page


@transactional
def replace_operation_hours(workshop_id: int, hours: list[dict]) -> None:
    """`PUT /workshop/operation-hours/` — substitui a lista inteira numa transação (BE-039).

    A trigger `fn_operation_hour_no_overlap` recusa intervalos sobrepostos no mesmo
    dia (consecutivos como 08–12 e 12–18 valem). Qualquer erro desfaz tudo: a
    oficina nunca fica sem os horários anteriores por causa de uma lista inválida.
    """
    if len(hours) > MAX_OPERATION_HOURS:
        raise ApiValidationFailure(
            {"detail": f"Informe no máximo {MAX_OPERATION_HOURS} intervalos."}
        )

    _lock_workshop(workshop_id)
    OperationHour.objects.filter(workshop_id=workshop_id).delete()
    try:
        with transaction.atomic():
            for hour in sorted(
                hours, key=lambda h: (h["day_of_week"], h["opening_time"])
            ):
                OperationHour.objects.create(workshop_id=workshop_id, **hour)
    except IntegrityError as exc:
        sqlstate, constraint, message = db_error_details(exc)
        if sqlstate == CHECK_VIOLATION and constraint is None and message:
            # Sobreposição (mensagem da trigger): é erro de validação da lista → 400.
            raise ApiValidationFailure({"detail": message}) from None
        raise


@transactional
def link_point(workshop_id: int, data: dict) -> PointOfInterest:
    """`POST /workshop/point/` — vincula um POI existente ou cria um e vincula (BE-040).

    O vínculo é 1:1 (UNIQUE em WORKSHOP.id_point_of_interest) e nunca é feito
    por proximidade. Trocar de ponto libera o anterior (que continua no mapa como POI).
    """
    workshop = _lock_workshop(workshop_id)

    point_id = data.get("id_point_of_interest")
    if point_id is not None:
        point = PointOfInterest.objects.filter(pk=point_id).first()
        if point is None:
            raise NotFound("Ponto do mapa não encontrado.")
        if (
            Workshop.objects.filter(point_of_interest=point)
            .exclude(pk=workshop_id)
            .exists()
        ):
            raise ApiConflict({"id_point_of_interest": [POINT_TAKEN]})
    else:
        point = PointOfInterest.objects.create(
            name=data["name"],
            type=data["type"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            address=data.get("address"),
        )

    workshop.point_of_interest = point
    workshop.save(update_fields=["point_of_interest"])
    return point
