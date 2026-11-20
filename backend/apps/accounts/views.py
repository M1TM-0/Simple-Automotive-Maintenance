from apps.accounts.models import Favorite
from apps.accounts.serializers import (
    AccountUpdateSerializer,
    ChangePasswordSerializer,
    DetailSerializer,
    FavoriteCreateSerializer,
    FavoriteSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserEnvelopeSerializer,
)
from apps.accounts.services import (
    add_favorite,
    authenticate_account,
    change_account_password,
    confirm_password_reset,
    public_account,
    register_account,
    remove_favorite,
    request_password_reset,
    update_account_profile,
)
from apps.accounts.sessions import refresh_account_session, start_account_session
from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.core.permissions import IsAccountHolder, IsClient
from apps.core.throttles import (
    LoginRateThrottle,
    PasswordResetRateThrottle,
    RegisterRateThrottle,
    client_ip,
)
from apps.reviews.selectors import rating_annotations
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

INVALID_CREDENTIALS = "E-mail ou senha incorretos."


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    """`POST /auth/register/` — BE-026."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]
    serializer_class = RegisterSerializer

    @extend_schema(
        request=RegisterSerializer,
        responses={
            201: UserEnvelopeSerializer,
            400: DetailSerializer,
            409: DetailSerializer,
        },
        summary="Cadastra cliente ou oficina e abre sessão",
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account, role = register_account(
            serializer.validated_data, ip=client_ip(request)
        )
        start_account_session(request, account, role)
        return Response(
            {"user": public_account(account, role, request)},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """`POST /auth/login/` — BE-027 (com limite de taxa e bloqueio progressivo, BE-033)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: UserEnvelopeSerializer,
            401: DetailSerializer,
            403: DetailSerializer,
            429: DetailSerializer,
        },
        summary="Autentica por perfil e abre sessão",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = authenticate_account(
            data["role"], data["email"], data["password"], ip=client_ip(request)
        )
        if result is None:
            return Response(
                {"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
            )
        account, role = result
        start_account_session(request, account, role)
        return Response(
            {"user": public_account(account, role, request)}, status=status.HTTP_200_OK
        )


class LogoutView(APIView):
    """`POST /auth/logout/` — BE-029."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None}, summary="Encerra a sessão")
    def post(self, request):
        request.session.flush()
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CurrentAccountView(APIView):
    """`GET /auth/me/` — BE-029. Define o cookie `csrftoken` inclusive no 401."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: UserEnvelopeSerializer, 401: DetailSerializer},
        summary="Quem sou eu (e define o cookie CSRF)",
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "Autenticação necessária."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if user.is_staff:
            # Admin Django (DP-03), sem perfil de domínio.
            return Response(
                {
                    "user": {
                        "id": user.pk,
                        "role": "admin",
                        "name": user.get_full_name() or user.get_username(),
                        "email": user.email or None,
                        "setup_complete": True,
                    }
                }
            )
        return Response({"user": public_account(user.account, user.role, request)})


class AccountMeView(APIView):
    """`PATCH /me/` — BE-031. Edita nome, telefone e foto do próprio perfil."""

    permission_classes = [IsAccountHolder]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        request={
            "application/json": AccountUpdateSerializer,
            "multipart/form-data": AccountUpdateSerializer,
        },
        responses={
            200: UserEnvelopeSerializer,
            400: DetailSerializer,
            401: DetailSerializer,
        },
        summary="Edita o próprio perfil (cliente ou oficina)",
    )
    def patch(self, request):
        user = request.user
        serializer = AccountUpdateSerializer(
            data=request.data,
            partial=True,
            context={"request": request, "role": user.role},
        )
        serializer.is_valid(raise_exception=True)
        account = update_account_profile(user, serializer.validated_data)
        return Response({"user": public_account(account, user.role, request)})


class ChangePasswordView(APIView):
    """`POST /me/password/` — BE-031. Invalida as outras sessões; a atual continua válida."""

    permission_classes = [IsAccountHolder]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={204: None, 400: DetailSerializer, 401: DetailSerializer},
        summary="Troca a senha do usuário autenticado",
    )
    def post(self, request):
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = change_account_password(
            user,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )
        refresh_account_session(request, account, user.role)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(APIView):
    """`POST /auth/password-reset/` — BE-032. Resposta idêntica exista ou não o e-mail."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={204: None, 400: DetailSerializer, 429: DetailSerializer},
        summary="Solicita redefinição de senha (resposta genérica)",
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_password_reset(
            email=data["email"], role=data.get("role") or None, ip=client_ip(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(APIView):
    """`POST /auth/password-reset/confirm/` — BE-032."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={204: None, 400: DetailSerializer, 429: DetailSerializer},
        summary="Confirma a redefinição de senha com token assinado",
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirm_password_reset(
            token=serializer.validated_data["token"],
            new_password=serializer.validated_data["password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------- favoritos (BE-062)


@extend_schema_view(
    get=extend_schema(summary="Oficinas favoritas do cliente"),
    post=extend_schema(
        summary="Favorita uma oficina (idempotente)",
        description="201 quando cria; 200 com o mesmo item quando a oficina já era favorita.",
        request=FavoriteCreateSerializer,
        responses={
            201: FavoriteSerializer,
            200: OpenApiResponse(
                FavoriteSerializer, description="Já era favorita (nada muda)."
            ),
            **{k: ERROR_RESPONSES[k] for k in (400, 401, 403, 404)},
        },
    ),
)
class FavoriteListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = FavoriteSerializer
    queryset = Favorite.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return (
            Favorite.objects.filter(client_id=self.request.user.id)
            .select_related("workshop__page", "workshop__point_of_interest")
            .annotate(**rating_annotations("workshop_id"))
            .order_by("-date_creation", "-id_favorite")
        )

    def create(self, request, *args, **kwargs):
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        favorite, created = add_favorite(
            request.user.id, serializer.validated_data["id_workshop"]
        )
        instance = self.get_queryset().get(pk=favorite.pk)
        return Response(
            FavoriteSerializer(instance, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FavoriteDetailView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        summary="Remove favorito (id da rota = id_workshop)",
        responses={204: None, **{k: ERROR_RESPONSES[k] for k in (401, 403, 404)}},
    )
    def delete(self, request, id_workshop):
        remove_favorite(request.user.id, id_workshop)
        return Response(status=status.HTTP_204_NO_CONTENT)
