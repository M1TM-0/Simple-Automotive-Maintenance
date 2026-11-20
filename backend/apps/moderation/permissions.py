"""Permissões da administração/moderação (BE-035, DP-03).

O admin é um usuário Django `is_staff` que entra pelo Django Admin (`/admin/`),
fora do formulário público; a API o reconhece pela mesma sessão
(`AccountSessionAuthentication`). Todas as rotas `/api/admin/*` usam
`ADMIN_PERMISSIONS` — via `AdminViewMixin` (`apps/moderation/views.py`).
"""

from apps.core.permissions import IsAdmin

ADMIN_PERMISSIONS = [IsAdmin]

__all__ = ["ADMIN_PERMISSIONS", "IsAdmin"]
