# ADR 0026 — Staging local (https://sam.localhost) e E2E em Chromium e Firefox

- **Status:** Aceito (decisão do responsável no BE-094, 2026-11-18). Complementa o ADR
  0022 (o staging é a mesma implantação de produção) e o BE-082 (E2E).
- **Tarefas:** BE-082, BE-094

## Contexto

O aceite (BE-094) pedia staging com HTTPS e dados restaurados e decidir Firefox/WebKit.
Restrições: projeto acadêmico, sem domínio público, sem hospedagem, sem custo, sem expor a
máquina à rede.

## Decisão

**Staging local** (`deploy/staging/`, passo a passo em `backend/docs/STAGING.md`)
- A implantação de produção (`deploy/compose.prod.yml` + `deploy/deploy.sh`) num projeto
  Docker próprio, `sam-staging`: banco, mídia e backups em volumes próprios — o
  desenvolvimento (`sam_pgdata`, `sam_media_data`) nunca é tocado.
- `compose.staging.yml` publica o proxy **só no loopback** (127.0.0.1 e ::1, portas
  80/443).
- Endereço `https://sam.localhost` (`*.localhost` resolve para o loopback; RFC 6761).
- Certificado de uma **CA local criada com OpenSSL** (mesmo papel do mkcert, que não
  estava instalado e exigiria root para o repositório do sistema), com
  `nameConstraints` = `sam.localhost`: mesmo se a chave vazar, ela não assina nenhum
  outro domínio. Segredos, CA, certificado e estado ficam fora do repositório, em
  `~/.local/share/sam-staging` (0700).
- `staging.sh trust --install` instala a CA (nome restrito) no Chromium/Chrome e nos
  perfis do Firefox do usuário, se ele quiser; os testes não dependem disso.

**E2E**
- Playwright com **Chromium e Firefox**: a suíte inteira roda nos dois (fixture
  parametrizada; `SAM_E2E_BROWSERS` restringe). **WebKit fora do escopo.**
- Playwright atualizado de 1.41.0 para 1.65.2: o Firefox do 1.41 (Firefox 121, NSS
  antigo) não reconhece CA local num perfil criado pelo NSS atual do sistema
  (`SEC_ERROR_UNKNOWN_ISSUER` mesmo com a CA confiável no `cert9.db`); o Firefox 159 do
  1.65 reconhece. Assim o certificado é **validado** nos dois navegadores, sem
  `ignore_https_errors` (com controle negativo: sem a CA, o site é recusado).
- Suíte do staging (`tests/e2e/test_staging.py`, `pytest -m staging`): HTTPS, tiles e
  atribuição do OSM, oficinas do SAM e camada do OSM, fluxos essenciais; modo
  `SAM_STAGING_EXPECT_OVERPASS=down` para o ensaio de indisponibilidade.

## Consequências

- O staging local valida tudo o que a produção usa (TLS, Nginx, Gunicorn, rotinas,
  backup, monitor), menos o que depende de um servidor de verdade: certificado público
  (Let's Encrypt), DNS, cópia fora do servidor e rede externa.
- HSTS de 1 ano fica gravado nos navegadores para `sam.localhost` (só esse nome).
- `docker` precisa do grupo `docker` na sessão (nesta máquina: `newgrp docker` ou novo
  login).
