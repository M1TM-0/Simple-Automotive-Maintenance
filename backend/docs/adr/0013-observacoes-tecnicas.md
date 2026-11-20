# ADR 0013 — Observações técnicas separadas

- **Status:** Aceito por padrão — recomendação do backlog (DP-13), 2026-11
- **Tarefas:** BE-012, BE-049

## Contexto

O cliente escreve observações ao pedir o atendimento; a oficina precisa de anotações
próprias sem apagar o texto do cliente.

## Decisão

- Coluna `technical_notes` no atendimento (migration `attendances/0002`).
- `PATCH /workshop/attendances/{id}/` grava `technical_notes`; `observations` no corpo é
  aceito como sinônimo (nome usado pelo frontend) e nunca sobrescreve o pedido do cliente.
- A oficina não edita dados cadastrais do veículo (só km).

## Consequências

- Tela T19 lê `technical_notes` pelo normalizador do `api.js`.
