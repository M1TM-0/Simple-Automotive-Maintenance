from apps.accounts.models import AccountStatus, Client, Workshop
from apps.accounts.principal import Principal
from apps.accounts.sessions import fingerprint_matches, read_account_session
from apps.core.logging import set_log_user
from rest_framework.authentication import SessionAuthentication

ACCOUNT_MODELS = {"client": Client, "workshop": Workshop}


class AccountSessionAuthentication(SessionAuthentication):
    """Autentica Client/Workshop (sessão de domínio) e admin Django `is_staff`, com CSRF.

    - Sem sessão: devolve None → o DRF responde **401** (ver `authenticate_header`).
    - Sessão inválida (conta inexistente, não ativa ou senha trocada): a sessão é
      descartada e a requisição segue como anônima (401 nos endpoints protegidos).
    - Métodos não seguros de uma sessão válida exigem `X-CSRFToken` (403 sem ele).
    """

    def authenticate_header(self, request):
        # Sem este cabeçalho o DRF converte "não autenticado" em 403 (P-01).
        return "Session"

    def authenticate(self, request):
        # Admin/moderação (DP-03): usuário Django autenticado pelo Django Admin.
        user = getattr(request._request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            self.enforce_csrf(request)
            user.role = "admin"
            set_log_user("admin", user.pk)
            return user, user

        session = request.session
        role, account_id, fingerprint = read_account_session(session)
        if role is None and account_id is None:
            return None

        account = self._load_account(role, account_id)
        if (
            account is None
            or account.status != AccountStatus.ACTIVE
            or not fingerprint_matches(account, fingerprint)
        ):
            session.flush()
            return None

        self.enforce_csrf(request)
        set_log_user(role, account.pk)
        principal = Principal(account, role)
        return principal, principal

    @staticmethod
    def _load_account(role, account_id):
        model = ACCOUNT_MODELS.get(role)
        if model is None or isinstance(account_id, bool):
            return None
        try:
            account_id = int(account_id)
        except (TypeError, ValueError):
            return None
        if account_id <= 0:
            return None
        return model.objects.filter(pk=account_id).first()
