# ADR 0022 — Hospedagem, HTTPS, backup e provedor de tiles

- **Status:** Aceito por padrão — recomendação do backlog (DP-22), 2026-11. **Revisto no
  BE-094 (2026-11-18):** tiles → ADR 0024; RPO/RTO e agendamento do backup → ADR 0025;
  staging local → ADR 0026.
- **Tarefas:** BE-088 a BE-094

## Contexto

Infraestrutura, custo e conformidade dependem do responsável; a recomendação do backlog
era Docker Compose + Nginx + TLS e backup diário.

## Decisão

- **Hospedagem:** um servidor Linux com Docker Compose (`deploy/compose.prod.yml`):
  PostgreSQL 16, API (Gunicorn), rotinas, proxy Nginx, backup e monitor.
- **HTTPS:** TLS 1.2/1.3 no Nginx, HTTP → HTTPS, HSTS 1 ano (sem preload). Certificado
  Let's Encrypt (desafio HTTP-01 por webroot, RUNBOOK) ou o da instituição.
- **Backup:** diário (03h), cifrado com chave pública GPG, cópia fora do servidor por
  rclone, 14 dias locais e 30 fora. **RPO 24 h; RTO-alvo 2 h** (ensaio automatizado:
  restauração de ponta a ponta em menos de 1 min com a base de teste). WAL contínuo só se
  o responsável exigir RPO menor.
- **Tiles do mapa: PENDENTE.** Hoje o frontend usa `tile.openstreetmap.org`, cuja política
  de uso não cobre serviço em produção com tráfego relevante. Antes do go-live (FE-10):
  contratar um provedor (MapTiler, Stadia, Thunderforest…) ou servir tiles próprios, e
  atualizar `map.js`, a atribuição e o `img-src` de `deploy/nginx/snippets/csp-frontend.conf`.

## Consequências

- RPO/RTO e o provedor de tiles precisam do aceite do responsável (`backend/docs/ACEITE.md`).
- Uma única réplica da API: atualizar a versão causa alguns segundos de indisponibilidade
  (o Nginx responde 502 durante a troca).
