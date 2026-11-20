# ADR 0003 — Perfil de administração/moderação

- **Status:** Aceito por padrão — recomendação do backlog (DP-03), 2026-11
- **Tarefas:** BE-035, BE-073, BE-074, BE-075, BE-076, BE-078

## Contexto

Sem um perfil de administração, denúncias e solicitações de serviço personalizado
nunca são resolvidas, contas não são bloqueadas e o pagamento das divulgações não é
confirmado. As telas T27/T28 do frontend não foram construídas.

## Decisão

- Admin = usuário Django ativo com `is_staff` (sem tabela nova). Entra pelo Django
  Admin (`/admin/`), fora do login público; a API o reconhece pela mesma sessão
  (`AccountSessionAuthentication`) e exige CSRF nas escritas.
- Rotas da API em `/api/admin/*` (`AdminViewMixin`): visitante → 401, cliente/oficina → 403.
  Um teste percorre o URLconf e exige o mixin em toda rota nova.
- Até existirem T27/T28, o Django Admin é a interface provisória: contas (status,
  anonimização), catálogo global, pontos de interesse e divulgações.
- Toda ação de escrita vai para o logger `sam.audit` (quem, ação, alvo, resultado);
  as feitas pelo Django Admin também ficam no `LogEntry`.

## Consequências

- Em produção `/admin/` fica atrás de HTTPS e, se possível, de rede restrita (BE-085/BE-089).
- Moderador sem `is_superuser` precisa das permissões de modelo do Django para usar o Admin.
