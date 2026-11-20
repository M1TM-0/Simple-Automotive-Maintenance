from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AccountSessionAuthenticationScheme(OpenApiAuthenticationExtension):
    """Documenta a autenticação por cookie de sessão + CSRF usada pela API."""

    target_class = "apps.accounts.authentication.AccountSessionAuthentication"
    name = "sessionAuth"
    match_subclasses = True

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "sessionid",
            "description": (
                "Sessão de cliente/oficina (ou usuário Django is_staff). "
                "Métodos não seguros também exigem o cabeçalho X-CSRFToken."
            ),
        }
