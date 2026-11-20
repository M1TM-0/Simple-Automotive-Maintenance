# ADR 0025 — Backup e recuperação: RPO 24 h, RTO 8 h, prova por ensaio

- **Status:** Aceito (decisão do responsável no BE-094, 2026-11-18). Substitui o "RTO-alvo
  2 h" e o agendamento descritos no ADR 0022 (o resto do ADR 0022 continua valendo).
- **Tarefas:** BE-090, BE-094

## Contexto

O backup diário cifrado já existia (BE-090), com ensaio automatizado num banco de teste.
O responsável fixou **RPO 24 h e RTO 8 h** e pediu evidência operacional, não só scripts.
A primeira restauração real (staging, PostgreSQL 16) **falhou**: ver Consequências.

## Decisão

- **Backup diário** pelo serviço `backup` (`sam-backup-loop`): roda se não houve sucesso
  desde a última ocorrência de `BACKUP_HOUR` (03h no fuso do negócio) — como um cron que
  recupera o atraso (contêiner parado às 03h → roda ao voltar). Intervalo entre backups
  ≤ 24 h + 5 min. Monitor alerta backup com mais de 26 h. Antes de cada atualização o
  `deploy.sh` faz outro.
- **Conteúdo**: `pg_dump -Fc` + mídia + manifesto com, por tabela, a contagem de linhas
  **e o md5 do conteúdo** (md5 de cada linha, ordenados), tudo no mesmo snapshot do dump.
- **Armazenamento**: volume próprio `backups` (separado do volume ativo do banco e de
  qualquer dado de desenvolvimento), cifrado (GPG), 14 dias; cópia fora do servidor com
  rclone quando houver destino (opcional).
- **Restauração** (`sam-restore`): só em banco e mídia vazios; confere sha256 do arquivo,
  do dump e da lista de mídia, `pg_restore` em transação única, contagens, md5 do
  conteúdo de cada tabela e hash de cada imagem.
- **Prova**: `deploy/staging/staging.sh restore-drill` restaura o último backup num
  PostgreSQL 16 **isolado** (contêiner descartável, rede interna sem saída, dados em
  tmpfs), sobe a API de produção sobre ele (`check_schema`, `migrate --check`,
  `/api/health/ready/`) e cronometra cada etapa; relatório JSON em
  `~/.local/share/sam-staging/drills/`. Mensal em produção (RUNBOOK §7).
- Sem replicação, cluster ou WAL contínuo (desnecessários para RPO 24 h).

## Consequências

- Ensaio no staging local (18/11/2026): restauração + conferência em 0,8 s, total 5,6 s
  (banco pequeno de demonstração: 36 tabelas, 357 linhas, 1 imagem) — muito abaixo de 8 h.
  A medida vale para este volume; com mais dados o tempo cresce com o tamanho do dump
  (refaça o ensaio periodicamente e registre em `backend/docs/ACEITE.md`).
- **Defeito achado pelo ensaio real**: o `pg_dump` grava `search_path` vazio e
  `normalize_service_name()` (do `init.sql`) chamava `clean_service_name()` sem schema →
  o índice `uq_service_name_normalized` falhava e **nenhum backup era restaurável**.
  Corrigido pela migration `catalog/0002` (chamada qualificada, sem mudar o resultado). O
  ensaio automatizado anterior não pegava porque rodava com o `init.sql` já corrigido da
  P-21; a regressão agora tem teste próprio (`apps/catalog/tests/test_restore_search_path.py`).
- **Defeito achado na revisão do agendador**: a regra antiga (">20 h e hora certa",
  senão ">26 h") passava a rodar a cada 26 h quando a primeira execução era depois das
  07h — RPO real de 26 h por vários dias. Corrigido (teste de regressão).
- O RPO de 24 h depende do serviço `backup` estar no ar: o monitor alerta com 26 h.
