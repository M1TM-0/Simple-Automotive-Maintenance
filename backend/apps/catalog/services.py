"""Casos de uso do catálogo da oficina (BE-041, BE-042).

Duplicidades (mesmo serviço global, mesmo nome personalizado normalizado) são
garantidas pelos índices do banco e traduzidas em `db_errors` para 409 com o campo.
"""

from apps.catalog.models import Product, SolicitationStatus, WorkshopService
from apps.core.storage import apply_image_changes
from apps.core.transactions import transactional


@transactional
def add_workshop_service(workshop_id: int, data: dict) -> WorkshopService:
    """Inclui serviço do catálogo global ou personalizado (este nasce `pending`)."""
    common = {
        "workshop_id": workshop_id,
        "price_base": data["price_base"],
        "duration_estimate": data["duration_estimate"],
        "disponibility": data.get("disponibility", True),
        "description_local": data.get("description_local"),
    }
    if data.get("service") is not None:
        return WorkshopService.objects.create(service=data["service"], **common)

    return WorkshopService.objects.create(
        service=None,
        name_local=data["name_local"],
        suggested_category=data["suggested_category"],
        status_solicitation=SolicitationStatus.PENDING,
        **common,
    )


EDITABLE_SERVICE_FIELDS = (
    "description_local",
    "price_base",
    "duration_estimate",
    "disponibility",
)


@transactional
def update_workshop_service(
    workshop_service: WorkshopService, data: dict
) -> WorkshopService:
    """Edita preço, duração, descrição local e disponibilidade (nome e origem imutáveis)."""
    fields = [field for field in EDITABLE_SERVICE_FIELDS if field in data]
    for field in fields:
        setattr(workshop_service, field, data[field])
    if fields:
        workshop_service.save(update_fields=fields)
    return workshop_service


PRODUCT_FIELDS = (
    "name",
    "description",
    "category",
    "brand",
    "price",
    "disponibility",
    "active",
)


@transactional
def create_product(workshop_id: int, data: dict) -> Product:
    product = Product.objects.create(
        workshop_id=workshop_id,
        **{field: data[field] for field in PRODUCT_FIELDS if field in data},
    )
    if data.get("photo") is not None:
        apply_image_changes(product, {"photo": data["photo"]}, folder="products")
    return product


@transactional
def update_product(product: Product, data: dict) -> Product:
    """Edição parcial; `active=false` desativa (produto nunca é apagado: RESTRICT)."""
    product = Product.objects.select_for_update().get(pk=product.pk)
    fields = [field for field in PRODUCT_FIELDS if field in data]
    for field in fields:
        setattr(product, field, data[field])
    if fields:
        product.save(update_fields=fields)
    if "photo" in data:
        apply_image_changes(product, {"photo": data["photo"]}, folder="products")
    return product
