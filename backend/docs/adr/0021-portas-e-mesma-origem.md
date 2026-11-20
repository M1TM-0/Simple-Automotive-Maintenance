# ADR 0021 — Portas em desenvolvimento e mesma origem em produção

- **Status:** Aceito por padrão — recomendação do backlog (DP-21), 2026-11
- **Tarefas:** BE-001, BE-005, BE-034, BE-089

## Contexto

Cookies de sessão/CSRF entre origens diferentes exigem CORS com credenciais e cuidados
extras; em desenvolvimento a API e o frontend rodam separados.

## Decisão

- Desenvolvimento: API em 8000, frontend em 5500, origens explícitas no CORS/CSRF
  (nunca curinga com credenciais).
- Produção: **mesma origem** atrás do Nginx. A imagem do proxy troca `js/config.js` por
  `deploy/nginx/config.prod.js` (`API_BASE = window.location.origin`, sem mudar o
  `api.js`); `CORS_ALLOWED_ORIGINS` vazio; `CSRF_TRUSTED_ORIGINS = https://<domínio>`.

## Consequências

- Provado no navegador com a CSP de produção e CORS desligado
  (`tests/e2e/test_same_origin_csp.py`) e na subida real (`deploy/smoke-test.sh`).
- `file://` não é suportado com `DRIVER:'http'`.
