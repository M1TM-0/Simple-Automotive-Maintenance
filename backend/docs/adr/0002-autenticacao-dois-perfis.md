# ADR 0002 — Autenticação de dois perfis por sessão

- **Status:** Aceito por padrão — recomendação do backlog (DP-02), 2026-11
- **Tarefas:** BE-024 a BE-031, BE-033

## Contexto

Cliente e oficina ficam em tabelas separadas (`CLIENT`, `WORKSHOP`) com o mesmo e-mail
possível nas duas. O frontend é HTML + JS puro servido na mesma origem em produção e lê
o cookie `csrftoken` para enviar `X-CSRFToken`.

## Decisão

- Autenticação própria sobre a sessão do Django + CSRF; sem JWT.
- `AccountSessionAuthentication` põe em `request.user` um `Principal(role, id, account)`.
  A sessão guarda `sam_account_role`, `sam_account_id` e o *fingerprint* HMAC do
  `password_hash` (troca/redefinição de senha derruba as outras sessões).
- Login e cadastro: `flush` + `rotate_token`. Senhas em Argon2 (PBKDF2 aceito e
  re-hasheado). Visitante em rota protegida → 401 com `WWW-Authenticate: Session`.
- Limites por IP+e-mail e bloqueio progressivo no cache compartilhado (`DatabaseCache`).

## Consequências

- Atrás do Nginx o IP do cliente vem do `X-Forwarded-For` reescrito pelo proxy
  (`SAM_NUM_PROXIES=1`); sem proxy, `0` (nunca o cabeçalho do cliente — defeito corrigido
  na Fase 7).
- O administrador é outro mecanismo (usuário Django `is_staff`, ADR 0003).
