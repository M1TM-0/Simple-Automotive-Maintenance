# ADR 0019 — Limites de entrada e busca normalizada

- **Status:** Aceito por padrão — recomendação do backlog (DP-19), 2026-11
- **Tarefas:** BE-036, BE-086

## Contexto

Colunas `TEXT` não limitam nada; buscas com e sem acento precisam achar o mesmo item.

## Decisão

- Limites de texto = `maxlength` das telas (`apps/core/limits.py`); senha ≤ 128.
- Imagens até 5 MB e 4096 px; corpo até 1 MB (JSON) e 16 MB (multipart) → 413.
- Busca em minúsculas, espaços colapsados e **sem acentos** por `translate()` (sem a
  extensão `unaccent`).

## Consequências

- O Nginx aceita até 17 MB para o 413 em JSON do Django chegar ao frontend (BE-089).
