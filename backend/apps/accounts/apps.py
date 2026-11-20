from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        # Registra a extensão de schema da autenticação de sessão.
        from apps.accounts import schema  # noqa: F401
