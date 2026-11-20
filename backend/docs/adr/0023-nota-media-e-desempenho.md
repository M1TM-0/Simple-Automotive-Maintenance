# ADR 0023 — Nota média na consulta e metas de desempenho

- **Status:** Aceito por padrão — recomendação do backlog (DP-23), 2026-11; medições da Fase 6 (BE-083) anexadas
- **Tarefas:** BE-011, BE-059, BE-065, BE-067, BE-083

## Contexto

DP-23 recomendou calcular a nota média das oficinas **na consulta** (sem coluna
denormalizada) e só denormalizar se o teste de carga exigir. O frontend faz polling: o
chat aberto pede `GET /chats/{id}/messages/?after=…`, `GET /chats/{id}/` e `GET /chats/`
a cada 5 s; o sino pede `GET /notifications/unread-count/` a cada 60 s em toda tela
logada. O mapa agrega distância, horário e nota (RNF08, RNF12; FE-05).

## Decisão

1. **Nota média continua calculada na consulta** (`apps/reviews/selectors.py`,
   `rating_annotations`, só `published`). Os números abaixo não justificam a coluna
   denormalizada nem os gatilhos que ela exigiria.
2. **Metas** (p95 medido no cliente, API em gunicorn, banco PostgreSQL local):
   | Carga | Meta p95 | Medido |
   |---|---|---|
   | 200 usuários com chat aberto + sino (≈ 120 req/s) | ≤ 200 ms por rota | 9,6–14,7 ms |
   | Lista de chats do cliente com 100 conversas, sob a carga acima | ≤ 300 ms | 13,9 ms |
   | Toda leitura do contrato | consultas constantes (sem N+1) e ≤ 15 por requisição | 38/38 leituras constantes |
   | Consultas críticas com volume | nenhuma varredura sequencial em tabela ≥ 10 mil linhas | nenhuma |
3. **Nenhum índice novo**: os de `init.sql` + `core/0002` (BE-011) cobrem todos os
   planos medidos. Rever se uma rota nova reprovar `tests/perf/test_query_plans.py`.
4. **Escala**: a capacidade cresce com processos do gunicorn (BE-088 define
   `GUNICORN_WORKERS`); o banco não foi o gargalo em nenhuma rodada.

## Medições (2026-11-17)

Ambiente: máquina de desenvolvimento com 16 núcleos; PostgreSQL 18 local
(`fsync=off`, só para a medição); gunicorn 26 com `config.settings.prod`
(`--workers 4 --worker-class gthread --threads 8`, pool psycopg `DB_POOL_MAX=10` por
processo, cache em `DatabaseCache`); gerador de carga
`tests/perf/polling_load.py` (threads Python) **na mesma máquina** — acima de ~500
usuários o próprio gerador disputa CPU e a latência inclui a fila do cliente.

Volume semeado (o mesmo de `tests/perf/test_query_plans.py`): 2.000 oficinas públicas com
ponto no mapa, 2.000 clientes, 12.000 atendimentos, orçamentos e avaliações, 12.000
horários, 42.000 mensagens, 60.000 notificações; o cliente `carga1` tem 100 conversas.

### Polling (`polling_load.py run`)

| Usuários (+10 sessões da conta com 100 conversas) | Duração | Vazão | p95 total | Erros |
|---|---|---|---|---|
| 200 | 116 s | 120 req/s | 11,5 ms | 0 |
| 500 | 65 s | 287 req/s | 17,9 ms | 0 |
| 1000 | 66 s | 469 req/s (saturado) | 2.615 ms | 0 |

Por rota, com 200 usuários:

| Rota | Requisições | p50 | p95 | p99 | máx |
|---|---|---|---|---|---|
| `GET /chats/{id}/messages/?after=` | 4.439 | 7,5 ms | 14,7 ms | 19,3 ms | 47,7 ms |
| `GET /chats/{id}/` | 4.439 | 6,4 ms | 9,6 ms | 12,3 ms | 32,1 ms |
| `GET /chats/` | 4.439 | 6,9 ms | 10,4 ms | 13,3 ms | 38,0 ms |
| `GET /chats/` (100 conversas) | 221 | 9,8 ms | 13,9 ms | 15,6 ms | 17,3 ms |
| `GET /notifications/unread-count/` | 400 | 4,8 ms | 10,5 ms | 12,9 ms | 18,7 ms |

Com 1000 usuários a demanda (≈ 650 req/s) passa da capacidade dessa configuração
(~470 req/s): as requisições enfileiram (p95 2,6 s), mas nenhuma falha — sem 5xx, sem
esgotar o pool de conexões (o pool espera até `DB_POOL_TIMEOUT`). Isso também cobre a
pendência P-20 (concorrência do pool).

### Planos de execução (`test_query_plans.py`, `EXPLAIN ANALYZE`)

Tempo somado das consultas de cada rota, com o volume acima: mapa (raio 10 km) 0,19 ms;
mapa com busca e "aberto agora" 0,30 ms; perfil público com nota média 0,12 ms;
avaliações públicas 0,08 ms; vitrine 1,47 ms; lista de chats 0,11–0,12 ms; polling de
mensagens 0,08 ms; não lidas 0,04 ms; notificações 0,04 ms; quadro da oficina 0,09 ms;
clientes atendidos 0,11 ms. Nenhum `Seq Scan` em `message`, `notification`,
`attendance`, `budget`, `review` ou `operation_hour`.

**Observação (a acompanhar em staging):** numa rodada da suíte completa, com coordenadas
aleatórias na semeadura e o relógio real perto da meia-noite, o planejador escolheu um
*hash semi-join* com varredura sequencial de `operation_hour` (12 mil linhas) no filtro
"aberto agora" do mapa. Não se repetiu em 20 combinações de semente × horário; o teste
passou a usar semente fixa e relógio congelado (segunda, 10h, o caso mais pesado). Se
aparecer em staging (`EXPLAIN` do mapa com `open_now=true`), o candidato é um índice
`OPERATION_HOUR (day_of_week, opening_time) INCLUDE (closing_time, id_workshop)`.

## Consequências

- Rota nova entra automaticamente em `tests/perf/test_query_counts.py` (N+1) e, se for
  crítica, deve ser acrescentada à lista de `test_query_plans.py`.
- Repetir `polling_load.py` em staging (BE-094) com a configuração final do gunicorn e o
  Nginx na frente; registrar os números aqui.
- Se a nota média reprovar uma meta no futuro: coluna `rating_sum/rating_count` em
  `WORKSHOP` mantida por trigger de `REVIEW` (migration `RunSQL` de ida e volta).
