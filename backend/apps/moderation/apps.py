from django.apps import AppConfig


class ModerationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.moderation"

    def ready(self):
        # Conecta os receptores de login/logout de admin ao log de auditoria.
        from apps.moderation import audit  # noqa: F401
