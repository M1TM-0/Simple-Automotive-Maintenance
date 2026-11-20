# ADR 0008 — Quem cancela o atendimento e duplicidade

- **Status:** Aceito por padrão — recomendação do backlog (DP-08), 2026-11
- **Tarefas:** BE-045, BE-047, BE-050

## Contexto

A RN09 diz que só a oficina altera o status; o frontend deixa o cliente cancelar.

## Decisão

- Cliente e oficina cancelam até `in_progress` (o banco recusa depois).
- Sem restrição a atendimentos abertos duplicados para o mesmo veículo.
- Regra da aplicação: transição para o **mesmo** status → 409 (a trigger ignora UPDATE
  sem mudança).

## Consequências

- Notificação para a outra parte em todo cancelamento (BE-070).
