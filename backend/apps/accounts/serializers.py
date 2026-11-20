from apps.accounts.passwords import validate_password
from apps.core import limits
from apps.core.fields import ImageURLField
from apps.core.openapi import optional_response_fields
from apps.core.validators import validate_cnpj as validate_cnpj_value
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

ROLE_CHOICES = (("client", "Cliente"), ("workshop", "Oficina"))


def _password_errors(value):
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from None
    return value


class RegisterSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=limits.PASSWORD
    )
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    name_fantasy = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )
    name_responsible = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )
    cnpj = serializers.CharField(required=False, allow_blank=True, max_length=18)
    phone_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )

    def validate_cnpj(self, value):
        if not value:
            return value
        try:
            return validate_cnpj_value(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from None

    def validate_password(self, value):
        return _password_errors(value)

    def validate(self, attrs):
        role = attrs.get("role")
        required = (
            ("name",)
            if role == "client"
            else ("name_fantasy", "name_responsible", "cnpj")
        )
        errors = {
            field: ["Este campo é obrigatório."]
            for field in required
            if not (attrs.get(field) or "").strip()
        }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class LoginSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=limits.PASSWORD
    )


class AccountUpdateSerializer(serializers.Serializer):
    """`PATCH /me/` (JSON ou multipart). Campos fora desta lista — `email`, `cnpj`,
    `status`, `password_hash`… — são ignorados (o DRF descarta chaves desconhecidas).

    Cliente: `name`, `phone_number`, `photo_profile`.
    Oficina: `name` (= `name_fantasy`), `name_fantasy`, `name_responsible`,
    `phone_number`, `photo_profile` (foto da página).
    """

    name = serializers.CharField(required=False, max_length=255)
    name_fantasy = serializers.CharField(required=False, max_length=255)
    name_responsible = serializers.CharField(required=False, max_length=255)
    phone_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    photo_profile = ImageURLField(required=False)

    WORKSHOP_ONLY = ("name_fantasy", "name_responsible")

    def validate(self, attrs):
        if self.context.get("role") == "client":
            for field in self.WORKSHOP_ONLY:
                attrs.pop(field, None)
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=limits.PASSWORD
    )
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=limits.PASSWORD
    )

    def validate_new_password(self, value):
        return _password_errors(value)


class PasswordResetRequestSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES, required=False, allow_blank=True
    )
    email = serializers.EmailField(max_length=255)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """`{token, password}` (contrato); `new_password` é aceito como sinônimo."""

    token = serializers.CharField(max_length=limits.TOKEN)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        required=False,
        max_length=limits.PASSWORD,
    )
    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        required=False,
        max_length=limits.PASSWORD,
    )

    def validate(self, attrs):
        password = attrs.get("password") or attrs.get("new_password")
        if not password:
            raise serializers.ValidationError(
                {"password": ["Este campo é obrigatório."]}
            )
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from None
        attrs["password"] = password
        return attrs


@optional_response_fields("name_fantasy", "name_responsible")
class PublicAccountSerializer(serializers.Serializer):
    """Forma pública da conta devolvida pelos endpoints de autenticação
    (`name_fantasy`/`name_responsible` só para oficina)."""

    id = serializers.IntegerField(read_only=True)
    role = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True, allow_null=True)
    phone_number = serializers.CharField(read_only=True, allow_null=True)
    photo_profile = serializers.URLField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True, allow_null=True)
    setup_complete = serializers.BooleanField(read_only=True, allow_null=True)
    name_fantasy = serializers.CharField(
        read_only=True, allow_null=True, required=False
    )
    name_responsible = serializers.CharField(
        read_only=True, allow_null=True, required=False
    )


class UserEnvelopeSerializer(serializers.Serializer):
    user = PublicAccountSerializer(read_only=True)


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)


class FavoriteSerializer(serializers.Serializer):
    """Oficina favorita (contrato §8.1). `id` = `id_workshop` (usado no DELETE)."""

    id = serializers.IntegerField(source="workshop_id", read_only=True)
    id_favorite = serializers.IntegerField(source="pk", read_only=True)
    id_workshop = serializers.IntegerField(source="workshop_id", read_only=True)
    name_fantasy = serializers.CharField(source="workshop.name_fantasy", read_only=True)
    photo_profile = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.IntegerField(read_only=True)
    type = serializers.SerializerMethodField()
    date_creation = serializers.DateTimeField(read_only=True)

    def get_photo_profile(self, obj) -> str | None:
        from apps.core.fields import media_url

        page = getattr(obj.workshop, "page", None)
        return media_url(
            page.photo_profile if page else None, self.context.get("request")
        )

    def get_rating_avg(self, obj) -> float | None:
        from apps.reviews.selectors import round_rating

        return round_rating(getattr(obj, "rating_avg", None))

    def get_type(self, obj) -> str | None:
        point = obj.workshop.point_of_interest
        return point.type if point else None


class FavoriteCreateSerializer(serializers.Serializer):
    id_workshop = serializers.IntegerField(min_value=1)
