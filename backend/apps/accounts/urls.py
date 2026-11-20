from apps.accounts.views import (
    AccountMeView,
    ChangePasswordView,
    CurrentAccountView,
    FavoriteDetailView,
    FavoriteListCreateView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)
from django.urls import path

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", CurrentAccountView.as_view(), name="current-account"),
    path(
        "auth/password-reset/",
        PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # Conta do usuário autenticado (cliente/oficina), BE-031
    path("me/", AccountMeView.as_view(), name="account-me"),
    path("me/password/", ChangePasswordView.as_view(), name="account-me-password"),
    # Favoritos do cliente, BE-062 (id da rota = id_workshop)
    path("favorites/", FavoriteListCreateView.as_view(), name="favorites"),
    path(
        "favorites/<int:id_workshop>/",
        FavoriteDetailView.as_view(),
        name="favorite-detail",
    ),
]
