# ADR 0007 — Acesso da oficina ao histórico do veículo

- **Status:** Aceito por padrão — recomendação do backlog (DP-07), 2026-11
- **Tarefas:** BE-043, BE-055, BE-056

## Contexto

O histórico de manutenção é dado do cliente; a oficina precisa dele para atender bem.

## Decisão

- A oficina vê o histórico se `history_shared = true` **e** ela tem pelo menos um
  atendimento com o veículo. Fora disso: 403 com `detail` explicando.
- O histórico só cresce (sem PATCH/DELETE: 405).

## Consequências

- O cliente controla o compartilhamento pela tela do veículo; a regra é testada na matriz
  de autorização (BE-084).
