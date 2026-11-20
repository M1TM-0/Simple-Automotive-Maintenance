import factory
from apps.accounts.models import Client, Favorite, Workshop
from apps.attendances.models import Attendance, Budget, BudgetItem
from apps.catalog.models import Product, Service, ServiceCategory, WorkshopService
from apps.chat.models import Chat, Message
from apps.core.validators import cnpj_check_digits
from apps.notifications.models import Notification
from apps.promotions.models import Promotion, PromotionAdvertisement
from apps.reviews.models import Denunciation, Review
from apps.vehicles.models import RegisterMaintenance, Vehicle
from apps.workshops.models import OperationHour, PagWorkshop, PointOfInterest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

PASSWORD_HASH = make_password("SenhaTeste123")


def make_cnpj(number):
    base = f"{number:012d}"
    return base + cnpj_check_digits(base)


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    name = factory.Sequence(lambda n: f"Cliente {n}")
    email = factory.Sequence(lambda n: f"cliente{n}@exemplo.com")
    password_hash = PASSWORD_HASH


class PointOfInterestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PointOfInterest

    name = factory.Sequence(lambda n: f"Ponto {n}")
    type = "oficina"
    latitude = "-5.091200"
    longitude = "-42.803100"


class WorkshopFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Workshop

    name_fantasy = factory.Sequence(lambda n: f"Oficina {n}")
    name_responsible = "Responsável"
    email = factory.Sequence(lambda n: f"oficina{n}@exemplo.com")
    password_hash = PASSWORD_HASH
    cnpj = factory.Sequence(lambda n: make_cnpj(n + 1))


class PagWorkshopFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PagWorkshop

    workshop = factory.SubFactory(WorkshopFactory)
    description = "Página da oficina"


class OperationHourFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OperationHour

    workshop = factory.SubFactory(WorkshopFactory)
    day_of_week = 1
    opening_time = "08:00"
    closing_time = "12:00"


class VehicleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vehicle

    client = factory.SubFactory(ClientFactory)
    brand = "Fiat"
    model = "Uno"
    year_fabrication = 2015
    year_model = 2016
    plate = factory.Sequence(
        lambda n: (
            f"ABC{n % 10}{chr(65 + (n // 10) % 26)}{(n // 260) % 10}{(n // 2600) % 10}"
        )
    )
    fuel = "flex"
    exchange = "manual"
    mileage_km = 50000


class ServiceCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceCategory

    name = factory.Sequence(lambda n: f"Categoria de teste {n}")


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Serviço de teste {n}")
    category = factory.SubFactory(ServiceCategoryFactory)


class WorkshopServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorkshopService

    workshop = factory.SubFactory(WorkshopFactory)
    service = factory.SubFactory(ServiceFactory)
    price_base = "100.00"
    duration_estimate = 60


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    workshop = factory.SubFactory(WorkshopFactory)
    name = factory.Sequence(lambda n: f"Produto {n}")
    brand = "Marca"
    category = "Filtros"
    price = "30.00"


class AttendanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Attendance

    client = factory.SubFactory(ClientFactory)
    vehicle = factory.SubFactory(
        VehicleFactory, client=factory.SelfAttribute("..client")
    )
    workshop = factory.SubFactory(WorkshopFactory)
    mileage_km = 50100


class BudgetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Budget

    attendance = factory.SubFactory(AttendanceFactory)
    workshop = factory.SelfAttribute("attendance.workshop")


class BudgetItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BudgetItem

    budget = factory.SubFactory(BudgetFactory)
    workshop = factory.SelfAttribute("budget.workshop")
    item_type = "labor"
    description = "Mão de obra"
    quantity = "1"
    unit_price = "80.00"


class RegisterMaintenanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RegisterMaintenance

    vehicle = factory.SubFactory(VehicleFactory)
    service_name = "Troca de óleo"


class ChatFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Chat

    client = factory.SubFactory(ClientFactory)
    workshop = factory.SubFactory(WorkshopFactory)


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    chat = factory.SubFactory(ChatFactory)
    sender_client = factory.SelfAttribute("chat.client")
    content = "Olá"


class FavoriteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Favorite

    client = factory.SubFactory(ClientFactory)
    workshop = factory.SubFactory(WorkshopFactory)


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    client = factory.SubFactory(ClientFactory)
    title = "Título"
    message = "Mensagem"


class PromotionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Promotion

    workshop = factory.SubFactory(WorkshopFactory)
    title = "Promoção"
    type_discount = "percentage"
    discount_value = "10.00"
    date_start = factory.LazyFunction(
        lambda: timezone.now() - timezone.timedelta(days=1)
    )
    date_end = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(days=10)
    )


class PromotionAdvertisementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PromotionAdvertisement

    promotion = factory.SubFactory(PromotionFactory)
    image_url = "promotions/banner.png"
    date_start = factory.LazyFunction(lambda: timezone.now())
    date_end = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=5))
    advertising_price = "50.00"


class DenunciationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Denunciation

    client = factory.SubFactory(ClientFactory)
    promotion = factory.SubFactory(PromotionFactory)
    reason = "spam"


def deliver_attendance(attendance, *, executed_labor=False):
    """Conduz um atendimento pela máquina de estados até `delivered` via ORM."""
    from apps.attendances.models import AttendanceStatus, BudgetStatus

    budget = BudgetFactory(attendance=attendance)
    service = WorkshopServiceFactory(workshop=attendance.workshop)
    service_item = BudgetItemFactory(
        budget=budget,
        item_type="service",
        workshop_service=service,
        description="Troca de óleo",
        unit_price="100.00",
    )
    product = ProductFactory(workshop=attendance.workshop)
    part_item = BudgetItemFactory(
        budget=budget,
        item_type="product",
        product=product,
        service_item=service_item,
        description="Filtro",
        quantity="2",
        unit_price="30.00",
    )

    def move(status):
        attendance.status_attendance = status
        attendance.save(update_fields=["status_attendance"])

    move(AttendanceStatus.WAITING_APPROVAL)
    budget.status_budget = BudgetStatus.APPROVED
    budget.save(update_fields=["status_budget"])
    move(AttendanceStatus.IN_PROGRESS)

    for item in (service_item, part_item):
        item.execution_status = "executed"
        item.save(update_fields=["execution_status"])

    move(AttendanceStatus.COMPLETED)
    move(AttendanceStatus.DELIVERED)
    budget.refresh_from_db()
    return budget, service_item, part_item


def make_review(budget, **kwargs):
    return Review.objects.create(budget=budget, rating=5, **kwargs)


def make_ready_workshop():
    """Oficina com página e 1 serviço do catálogo (cadastro concluído, BE-028)."""
    workshop = PagWorkshopFactory().workshop
    WorkshopServiceFactory(workshop=workshop)
    return workshop


def jpeg_upload(name="foto.jpg", size=(40, 30)):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def fake_image_upload(name="foto.jpg"):
    """Arquivo com extensão de imagem e conteúdo HTML (deve ser recusado, BE-021)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name, b"<html><script>alert(1)</script></html>", content_type="image/jpeg"
    )


def stored_name(url):
    """`http://testserver/media/vehicles/x.jpg` → `vehicles/x.jpg`."""
    return url.split("/media/", 1)[1]
