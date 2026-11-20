# ADR 0017 — Mapa por caixa envolvente + Haversine

- **Status:** Aceito por padrão — recomendação do backlog (DP-17), 2026-11
- **Tarefas:** BE-011, BE-067, BE-083

## Contexto

O mapa é a porta de entrada do produto; PostGIS aumentaria a operação (imagem,
extensão, backup) para um volume modesto.

## Decisão

- Filtro por caixa envolvente (índices de latitude/longitude) e distância exata por
  Haversine em SQL; raio padrão 10 km, máximo 100 km (400 acima).
- UNION de oficinas públicas e pontos de interesse; filtro de categoria devolve só oficinas
  (ponto não tem serviços).

## Consequências

- Medido em BE-083 (ADR 0023): 0,19 ms de consulta com 2.000 oficinas. Rever (PostGIS)
  se o volume crescer muito.
