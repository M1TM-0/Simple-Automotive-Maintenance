# ADR 0006 — Regra de cadastro oficial concluído (`setup_complete`)

- **Status:** Aceito por padrão — recomendação do backlog (DP-06), 2026-11
- **Tarefas:** BE-001, BE-028

## Contexto

A RN02 cita dados, endereço e serviços; a tela T17 (assistente) exige só um serviço e
trata ponto no mapa e horários como opcionais.

## Decisão

- `setup_complete` = oficina com **pelo menos 1 serviço** não rejeitado.
- Ponto e horários não são exigidos. A divergência com a RN02 (endereço) fica registrada
  para o responsável.
- Rotas `/workshop/*` exigem `IsWorkshopSetupComplete`, exceto as do assistente (`me`,
  `page`, `operation-hours`, `point`, `services`, `points-of-interest`); um teste percorre
  o URLconf e reprova rota nova sem a permissão.

## Consequências

- A mesma régua define a oficina pública (ADR 0020).
