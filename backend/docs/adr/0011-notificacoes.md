# ADR 0011 — Notificações geradas pela aplicação

- **Status:** Aceito por padrão — recomendação do backlog (DP-11), 2026-11
- **Tarefas:** BE-010, BE-069, BE-070

## Contexto

O sino do frontend lista eventos (solicitação, orçamento, mensagens, avaliações,
moderação, manutenção).

## Decisão

- Geradas por `apps/notifications/events.py`, gravadas no `on_commit` (nunca para uma
  transação desfeita) e sem derrubar a operação (erro vai para o log).
- `url` interna (página `.html` do frontend, validada por CHECK); sem e-mail.
- Chat: uma notificação não lida por conversa.

## Consequências

- O orçamento vencido pela rotina de expiração notifica o cliente uma vez.
