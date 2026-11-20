"""Permissões por perfil e por objeto (BE-030) e o bloqueio do cadastro da oficina (BE-028).

Visitante em endpoint protegido → 401 (a autenticação define `WWW-Authenticate`);
perfil errado → 403; recurso de outro dono → 404 (querysets filtrados pelos
mixins de `apps/core/mixins.py`).
"""

from apps.workshops.domain import is_setup_complete
from rest_framework.permissions import BasePermission


def _role(request):
    return getattr(request.user, "role", None)


def _authenticated(request):
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated)


class IsClient(BasePermission):
    message = "Esta ação é exclusiva para clientes."

    def has_permission(self, request, view):
        return _authenticated(request) and _role(request) == "client"


class IsWorkshop(BasePermission):
    message = "Esta ação é exclusiva para oficinas."

    def has_permission(self, request, view):
        return _authenticated(request) and _role(request) == "workshop"


class IsAccountHolder(BasePermission):
    """Cliente ou oficina (rotas de conta como `/me/`); admin Django não tem perfil de domínio."""

    message = "Esta ação é exclusiva para clientes e oficinas."

    def has_permission(self, request, view):
        return _authenticated(request) and _role(request) in ("client", "workshop")


class IsAdmin(BasePermission):
    """Administração/moderação (DP-03): usuário Django ativo com `is_staff`."""

    message = "Esta ação é exclusiva para administradores."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            _authenticated(request)
            and getattr(user, "is_staff", False)
            and getattr(user, "is_active", False)
        )


class IsChatParticipant(BasePermission):
    """Só o cliente e a oficina da conversa alcançam o chat (ou a mensagem dele)."""

    message = "Você não participa desta conversa."

    def has_permission(self, request, view):
        return _authenticated(request) and _role(request) in ("client", "workshop")

    def has_object_permission(self, request, view, obj):
        chat = getattr(obj, "chat", obj)
        role = _role(request)
        if role == "client":
            return chat.client_id == request.user.id
        if role == "workshop":
            return chat.workshop_id == request.user.id
        return False


class IsWorkshopSetupComplete(BasePermission):
    """Bloqueia as rotas administrativas da oficina até o cadastro oficial (RN02, DP-06).

    Use sempre depois de `IsWorkshop` (para outros perfis ela não decide nada).
    """

    message = "Conclua o cadastro da oficina para acessar este recurso."

    def has_permission(self, request, view):
        if _role(request) != "workshop":
            return True
        return is_setup_complete(request.user.account)


# Conjuntos usados pelas rotas `/workshop/*` (BE-028). Toda rota nova da oficina
# usa WORKSHOP_PERMISSIONS, exceto as do assistente T17, que usam
# WORKSHOP_WIZARD_PERMISSIONS. `apps/core/tests/test_permissions.py` confere isso
# percorrendo o URLconf.
WORKSHOP_PERMISSIONS = [IsWorkshop, IsWorkshopSetupComplete]
WORKSHOP_WIZARD_PERMISSIONS = [IsWorkshop]
WORKSHOP_WIZARD_ROUTES = frozenset(
    {"me", "page", "operation-hours", "point", "services", "points-of-interest"}
)
