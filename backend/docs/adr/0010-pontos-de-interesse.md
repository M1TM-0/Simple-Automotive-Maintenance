# ADR 0010 — Origem e licença dos pontos de interesse

- **Status:** Aceito por padrão — recomendação do backlog (DP-10), 2026-11. **Fonte decidida
  no BE-094 (2026-11-18): ver ADR 0024** (OpenStreetMap pela Overpass, além do SAM).
- **Tarefas:** BE-071

## Contexto

Sem pontos de interesse o mapa mostra só oficinas cadastradas.

## Decisão

- Carga por `manage.py import_pois --file … --source …` (CSV ou GeoJSON), idempotente
  por `external_source` + `external_id`, com `--dry-run` e relatório.
- Só os campos que a licença da fonte permite (nome, tipo, coordenadas, endereço).

## Consequências

- **Pendente com o responsável:** escolher a fonte. Dados do OpenStreetMap são ODbL:
  exigem atribuição visível e compartilhamento pela mesma licença do banco derivado.
- Passo da primeira implantação (RUNBOOK).
