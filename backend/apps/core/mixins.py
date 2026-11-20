"""Padrão de dono (anti-BOLA, BE-030).

O queryset é sempre filtrado pelo `Principal` autenticado: um recurso de outro
dono simplesmente não existe para a view e o `get_object()` responde **404**
(não vaza existência). Perfil errado deve ser barrado antes, pelas permissões
(`IsClient`/`IsWorkshop` → 403); se chegar aqui, o queryset vem vazio.

`owner_lookup` aceita caminhos aninhados, ex.: `"vehicle__client_id"` ou
`"budget__workshop_id"`.
"""


def is_schema_generation(view) -> bool:
    """True quando o drf-spectacular instancia a view só para gerar o schema."""
    return getattr(view, "swagger_fake_view", False)


class _OwnedByPrincipalMixin:
    owner_role = None
    owner_lookup = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_schema_generation(self):
            return queryset.none()
        user = self.request.user
        if (
            not getattr(user, "is_authenticated", False)
            or getattr(user, "role", None) != self.owner_role
        ):
            return queryset.none()
        return queryset.filter(**{self.owner_lookup: user.id})


class OwnedByClientMixin(_OwnedByPrincipalMixin):
    owner_role = "client"
    owner_lookup = "client_id"


class OwnedByWorkshopMixin(_OwnedByPrincipalMixin):
    owner_role = "workshop"
    owner_lookup = "workshop_id"


class PublicCacheMixin:
    """Leitura pública que muda raramente (catálogo, BE-036): `Cache-Control` curto."""

    cache_max_age = 300

    def finalize_response(self, request, response, *args, **kwargs):
        from django.utils.cache import patch_cache_control

        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method == "GET" and response.status_code == 200:
            patch_cache_control(response, public=True, max_age=self.cache_max_age)
        return response
