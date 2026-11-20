# ADR 0016 — Fuso horário único do negócio

- **Status:** Aceito por padrão — recomendação do backlog (DP-16), 2026-11
- **Tarefas:** BE-001, BE-022, BE-065, BE-090

## Contexto

Horários de funcionamento são `TIME` sem fuso; "aberto agora" e validades dependem do fuso.

## Decisão

- Um fuso único configurável, `SAM_TIME_ZONE` (padrão `America/Sao_Paulo`); `USE_TZ`.
- `business_clock()`/`is_open_at()` em Python e a mesma régua em SQL no mapa.
- O agendador do backup usa o mesmo fuso (`TZ`) para a hora do backup diário.

## Consequências

- Com `SAM_TIME_ZONE=UTC` (máquina de desenvolvimento) o "aberto agora" sai 3 h adiantado.
