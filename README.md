# SAM — Simple Automotive Maintenance

> *Your car • Your care* — plataforma web que conecta donos de veículos (**Cliente**) a
> oficinas e mecânicos (**Oficina**): mapa, solicitação de atendimento, orçamento, chat,
> histórico de manutenção, avaliações e promoções.

**Projeto acadêmico.** O SAM foi desenvolvido como trabalho em grupo de graduação. Ele
**não está em produção**, não é comercializado e não é oferecido como serviço. Este
repositório existe para apresentar o trabalho e permitir que outras pessoas consultem,
executem e avaliem o código.

---

## Sumário

1. [O problema](#1-o-problema)
2. [Funcionalidades](#2-funcionalidades)
3. [Tecnologias](#3-tecnologias)
4. [Arquitetura](#4-arquitetura)
5. [Estrutura do repositório](#5-estrutura-do-repositório)
6. [Pré-requisitos](#6-pré-requisitos)
7. [Configuração do ambiente](#7-configuração-do-ambiente)
8. [Execução local](#8-execução-local)
9. [Banco de dados](#9-banco-de-dados)
10. [Testes e verificações](#10-testes-e-verificações)
11. [Implantação (referência)](#11-implantação-referência)
12. [Documentação](#12-documentação)
13. [Como contribuir ou reportar problemas](#13-como-contribuir-ou-reportar-problemas)
14. [Créditos de terceiros](#14-créditos-de-terceiros)
15. [Autoria e licença](#15-autoria-e-licença)

---

## 1. O problema

O projeto parte de dificuldades comuns na relação entre proprietários de veículos e
prestadores de serviços automotivos (detalhadas em [`backlog/backlog.md`](backlog/backlog.md)):

- **Encontrar a oficina certa.** Nem toda oficina faz todo serviço, e o cliente costuma
  precisar ligar para várias até achar quem resolva um problema específico.
- **Falta de informação antes do contato.** Serviços, especialidades, produtos,
  promoções e reputação raramente estão reunidos num só lugar.
- **Serviços pontuais.** Às vezes basta uma borracharia ou um posto com calibragem por
  perto, não uma oficina completa.
- **Comunicação fragmentada** entre cliente e oficina.
- **Divulgação e gestão para pequenos prestadores**, que muitas vezes não têm site próprio
  nem uma ferramenta para organizar atendimentos, orçamentos e histórico dos veículos.

O SAM propõe uma plataforma única: o cliente encontra oficinas pelo mapa e pelos
serviços oferecidos, conversa com elas, solicita atendimento e acompanha o orçamento e a
execução. A oficina mantém uma página pública e uma área de gestão.

## 2. Funcionalidades

O frontend tem 26 telas (lista completa em [`frontend/README.md`](frontend/README.md)).

**Cliente**
- Cadastro, login, recuperação de senha e edição da conta.
- Mapa com busca por nome ou serviço, categoria e "aberto agora". Mostra as oficinas do
  SAM e, com zoom suficiente, estabelecimentos do OpenStreetMap obtidos pela Overpass API.
- Perfil público da oficina: serviços, horários, produtos, promoções vigentes e avaliações.
- Oficinas favoritas.
- Garagem: cadastro de veículos com fotos, histórico de manutenção (registros manuais e
  feitos pela oficina) e próximas manutenções preventivas, com lembretes.
- Solicitação de atendimento, aprovação ou recusa do orçamento e acompanhamento das etapas.
- Chat com a oficina e notificações no sino.
- Avaliação do atendimento e denúncia de avaliações, promoções e divulgações.

**Oficina**
- Assistente de cadastro oficial (dados do estabelecimento, ponto no mapa, horários e serviços).
- Página pública, serviços oferecidos e catálogo de produtos. O catálogo só informa o que
  existe na oficina: **não há venda pela plataforma**.
- Quadro e lista de atendimentos, editor de orçamento (peças, mão de obra e serviços),
  execução dos itens, observações técnicas e entrega do veículo.
- Clientes e veículos atendidos, com acesso ao histórico quando o cliente o compartilha.
- Promoções e divulgação paga com confirmação manual do pagamento (não há gateway de pagamento).
- Respostas às avaliações recebidas.

**Administração**
- Django Admin e rotas `/api/admin/*`: moderação de denúncias, solicitações de serviços
  personalizados, bloqueio, desativação e anonimização de contas, confirmação de
  divulgações pagas. As telas próprias de moderação (T27/T28) não foram construídas.

**Rotinas em segundo plano**
- Serviço `jobs`: expiração de orçamentos e promoções, ativação e encerramento das
  divulgações pagas e lembretes de manutenção preventiva.

## 3. Tecnologias

| Camada | Tecnologias |
|---|---|
| Frontend | HTML5, CSS3 e JavaScript puro, sem framework e sem etapa de build. Mapa com [Leaflet](https://leafletjs.com/) 1.9.4 (CDN com SRI) e tiles do OpenStreetMap. |
| Backend | Python 3.12, Django 5.2, Django REST Framework, drf-spectacular (OpenAPI/Swagger), django-filter, django-cors-headers, django-environ, Pillow, psycopg 3 (com pool), Argon2, Gunicorn. |
| Banco | PostgreSQL 16. Schema, regras e triggers em [`database/init.sql`](database/init.sql). |
| Infra de desenvolvimento | Docker e Docker Compose. |
| Implantação (referência) | Docker Compose de produção, Nginx (TLS, mesma origem, CSP), backup cifrado com GPG, monitor com alertas. |
| Qualidade | pytest, pytest-django, factory-boy, pytest-cov, Playwright (Chromium e Firefox), Ruff, pip-audit, Gitleaks, pre-commit, GitHub Actions. |

Versões exatas: [`backend/requirements/base.txt`](backend/requirements/base.txt) e
[`backend/requirements/dev.txt`](backend/requirements/dev.txt).

## 4. Arquitetura

```
 Navegador ── frontend estático (HTML/CSS/JS) ── js/api.js ──HTTP/JSON──▶ API REST (Django + DRF)
                                                                             │
                                          jobs (expirações, lembretes) ──────┤
                                                                             ▼
                                                     PostgreSQL 16 (init.sql: schema, triggers, funções)
```

- **Frontend:** cada tela tem seu HTML, CSS e JS. Toda chamada de dados passa por
  `frontend/js/api.js`, a única porta para a API. Regras de negócio ficam no backend; a
  interface valida formato e exibe as mensagens de erro da API.
- **Backend em camadas:** `views` (HTTP) → `serializers` (forma e validação) → `services`
  (casos de uso, transacionais) → `models`. Os apps de domínio ficam em `backend/apps/`
  (`accounts`, `attendances`, `catalog`, `chat`, `core`, `moderation`, `notifications`,
  `promotions`, `reviews`, `vehicles`, `workshops`).
- **O banco é a autoridade das invariantes:** `database/init.sql` é a fonte do schema e
  é aplicado pela migration `core/0001`. Os modelos Django são `managed=False`, e os
  erros de triggers e restrições são traduzidos em respostas HTTP (409 com a mensagem do banco).
- **Autenticação** por sessão do Django com CSRF, dois perfis (Cliente e Oficina) e um
  perfil de administração (usuário `is_staff`).
- **Desenvolvimento:** API na porta 8000 e frontend na 5500 (CORS liberado só para essa
  origem). **Produção:** Nginx serve frontend e API na mesma origem.

As decisões estão registradas em 26 ADRs: [`backend/docs/adr/`](backend/docs/adr/README.md).
Diagrama do banco: [`docs/DIAGRAMA_SAM.svg`](docs/DIAGRAMA_SAM.svg). Diagrama de uso:
[`docs/DIAGRAMA_DE_USO.svg`](docs/DIAGRAMA_DE_USO.svg).

## 5. Estrutura do repositório

```
.
├── backend/                 API Django
│   ├── apps/                apps de domínio (cada um com seus testes em tests/)
│   ├── config/              settings (base, dev, test, prod), urls, wsgi/asgi
│   ├── tests/               testes transversais: segurança, contrato, regras do banco,
│   │                        concorrência, desempenho, E2E e implantação
│   ├── docs/                ADRs, runbook, staging, segurança, aceite
│   ├── requirements/        base.txt (aplicação) e dev.txt (testes e ferramentas)
│   ├── Dockerfile           imagens de produção (alvos api e proxy)
│   └── Dockerfile.dev       imagem de desenvolvimento
├── frontend/                HTML, CSS, JS e imagens (sem build)
├── database/init.sql        schema, triggers, funções e dados iniciais do catálogo
├── deploy/                  produção de referência: compose, Nginx, backup, deploy.sh, staging
├── docs/                    diagramas e registro do desenvolvimento
├── backlog/                 requisitos do produto e backlog do backend
├── docker-compose.yaml      ambiente de desenvolvimento (db, api, jobs, web)
├── setup.sh                 cria os arquivos .env de desenvolvimento
└── .github/workflows/       CI (lint, testes, segurança, E2E, ensaio de implantação)
```

## 6. Pré-requisitos

**Com Docker (recomendado)**
- Docker Engine e o plugin Docker Compose v2.
- `python3`, usado só pelo `setup.sh` para gerar valores aleatórios.
- Portas livres: 5432 (PostgreSQL), 8000 (API) e 5500 (frontend).

**Sem Docker**
- Python 3.12.
- PostgreSQL 16 (o CI usa o 16).
- Node.js, só para os testes de contrato, que executam os normalizadores do `frontend/js/api.js`.
- Para os testes E2E: navegadores do Playwright (`python -m playwright install chromium firefox`).

## 7. Configuração do ambiente

Os arquivos `.env` reais **não são versionados**. O repositório traz só os modelos:

| Modelo | Gera | Usado por |
|---|---|---|
| [`.env.example`](.env.example) | `.env` | Docker Compose (credenciais do PostgreSQL de desenvolvimento) |
| [`backend/.env.example`](backend/.env.example) | `backend/.env` | Django (todas as variáveis comentadas) |
| [`deploy/.env.prod.example`](deploy/.env.prod.example) | `deploy/.env.prod` | implantação de referência (ver seção 11) |

Para desenvolvimento, basta rodar:

```bash
./setup.sh
```

O script cria `.env` e `backend/.env` a partir dos modelos, com senha do banco e
`SECRET_KEY` aleatórias e permissão `600`. **Ele nunca sobrescreve um `.env` existente.**

## 8. Execução local

### Com Docker Compose

```bash
./setup.sh                  # uma vez
docker compose up --build   # a migration aplica o init.sql automaticamente
```

| Serviço | Endereço |
|---|---|
| Frontend | http://localhost:5500/ |
| API (saúde) | http://localhost:8000/api/health/ |
| Swagger (com `DEBUG=True`) | http://localhost:8000/api/docs/ |
| Django Admin | http://localhost:8000/admin/ |

Contas de Cliente e de Oficina são criadas pela própria interface, em "Criar conta". Para
usar o Django Admin, crie um superusuário:

```bash
docker compose exec api python manage.py createsuperuser
```

### Sem Docker

```bash
cd backend
python3.12 -m venv venv
venv/bin/pip install -r requirements/dev.txt
cp .env.example .env        # ajuste SECRET_KEY e DATABASE_URL (seu PostgreSQL)
venv/bin/python manage.py migrate
venv/bin/python manage.py runserver 8000
```

Em outro terminal, sirva o frontend na porta 5500, que é a origem liberada no CORS:

```bash
cd frontend
python3 -m http.server 5500
```

O frontend também abre sem servidor (`DRIVER:'local'` em `frontend/js/config.js`). Nesse
modo, apenas login, veículos e conversas do cliente funcionam, salvos no `localStorage`.
Detalhes em [`frontend/README.md`](frontend/README.md).

## 9. Banco de dados

- **Fonte do schema:** [`database/init.sql`](database/init.sql) (tabelas, views, triggers,
  funções e dados iniciais das categorias e serviços do catálogo). A migration `core/0001`
  o executa uma única vez; mudanças posteriores são migrations `RunSQL` com ida e volta.
  Não reexecute o `init.sql` à mão.
- **Conexão:** `DATABASE_URL` (por exemplo, `postgres://sam:senha@localhost:5432/sam`). No
  Docker Compose ela é montada a partir de `POSTGRES_USER`, `POSTGRES_PASSWORD` e
  `POSTGRES_DB` do `.env` da raiz.
- **Criar ou atualizar o schema:** `python manage.py migrate`.
- **Conferir o banco contra o `init.sql` e as migrations:** `python manage.py check_schema`.
- **Regerar o diagrama:** `python manage.py schema_diagram`. Um teste reprova se
  `docs/DIAGRAMA_SAM.svg` ficar desatualizado.
- Mais detalhes: [`backend/docs/migrations.md`](backend/docs/migrations.md) e o ADR 0001.

## 10. Testes e verificações

Os testes usam **PostgreSQL de verdade** (nunca SQLite). Aponte `TEST_DATABASE_URL` (ou
`DATABASE_URL`) para um banco em que o usuário possa criar o banco de teste. Comandos a
partir de `backend/`:

```bash
venv/bin/ruff check .                     # lint
venv/bin/ruff format --check .            # formatação
DJANGO_SETTINGS_MODULE=config.settings.test venv/bin/python manage.py makemigrations --check --dry-run
venv/bin/pytest                           # suíte padrão (sem E2E e staging)
venv/bin/pytest --cov                     # com cobertura (meta geral: 90%)
venv/bin/pytest -m db_rules               # só as regras do banco (triggers e funções)
venv/bin/pytest -m deploy                 # artefatos de implantação (Gunicorn, Nginx, deploy.sh, backup)
venv/bin/pytest -m e2e                    # ponta a ponta no navegador (Chromium e Firefox)
venv/bin/python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
venv/bin/pip-audit -r requirements/dev.txt
```

- O ensaio de backup e restauração (`tests/deploy/test_backup_restore.py`) precisa de
  `pg_dump`/`pg_restore` **da mesma versão** do servidor PostgreSQL. Sem isso, ele é pulado.
- `../deploy/smoke-test.sh` faz uma implantação real com Docker (imagens, TLS
  autoassinado, backup e restauração).
- O CI ([`.github/workflows/backend-tests.yml`](.github/workflows/backend-tests.yml)) roda
  lint, testes com cobertura, schema OpenAPI, `check --deploy`, auditoria de dependências,
  varredura de segredos (Gitleaks), E2E e o ensaio de implantação.
- Ganchos locais: `pip install pre-commit && pre-commit install`
  ([`.pre-commit-config.yaml`](.pre-commit-config.yaml)).

## 11. Implantação (referência)

O projeto inclui uma implantação completa de referência (Docker Compose de produção,
Nginx com TLS, backup cifrado, monitor e alertas), usada nos testes e no ensaio local.
**O SAM não está implantado em nenhum servidor público.** Para quem quiser estudar ou
reproduzir:

- Passo a passo: [`backend/docs/RUNBOOK.md`](backend/docs/RUNBOOK.md).
- Staging local isolado: [`backend/docs/STAGING.md`](backend/docs/STAGING.md).
- Decisões de segurança: [`backend/docs/seguranca/`](backend/docs/seguranca/).

## 12. Documentação

| Documento | Conteúdo |
|---|---|
| [`backlog/backlog.md`](backlog/backlog.md) | Requisitos do produto (objetivos, público, problema, RF, RNF, regras de negócio). |
| [`backlog/backlog_backend.md`](backlog/backlog_backend.md) | Especificação do backend: tarefas, contrato da API, regras, plano de testes. |
| [`backend/docs/adr/`](backend/docs/adr/README.md) | Registros de decisões de arquitetura (ADRs). |
| [`frontend/PENDENCIAS-API.md`](frontend/PENDENCIAS-API.md) | Contrato consumido pelo frontend. |
| [`docs/DESENVOLVIMENTO.md`](docs/DESENVOLVIMENTO.md) | Registro técnico do desenvolvimento: estado por fase, convenções e armadilhas conhecidas, registro das sessões. |
| [`AUDITORIA.md`](AUDITORIA.md) | Auditoria interna das fases 0 a 2 (registro histórico). |
| [`backend/docs/ACEITE.md`](backend/docs/ACEITE.md) | Evidências da validação final. |
| Swagger / OpenAPI | `/api/docs/` e `/api/schema/` com a API rodando (`DEBUG=True`). |

## 13. Como contribuir ou reportar problemas

- **Problemas e sugestões:** abra uma *issue* neste repositório descrevendo o que
  aconteceu, como reproduzir e o resultado esperado.
- **Contribuições:** por ser um trabalho acadêmico, a incorporação de mudanças depende da
  avaliação dos autores. Antes de propor um *pull request*, abra uma *issue* para discutir
  a ideia. Mantenha as verificações da seção 10 passando (Ruff, testes e Gitleaks).
- **Segurança:** não publique credenciais em *issues*. Os valores dos arquivos
  `*.example` são apenas modelos.

## 14. Créditos de terceiros

- **Leaflet** 1.9.4, carregado por CDN (unpkg): <https://leafletjs.com/>.
- **OpenStreetMap:** tiles e dados de estabelecimentos (Overpass API) © colaboradores do
  OpenStreetMap, sob a licença ODbL. A atribuição aparece no próprio mapa:
  <https://www.openstreetmap.org/copyright>.
- **Google Fonts:** Playfair Display e Poppins, carregadas de `fonts.googleapis.com`.
- **Dependências Python:** instaladas pelo `pip` a partir dos arquivos de
  `backend/requirements/`, cada uma sob a sua própria licença.

## 15. Autoria e licença

- **Autoria:** projeto acadêmico desenvolvido em grupo. Os créditos dos integrantes
  serão adicionados pelos próprios autores.
- **Licença:** o código deste repositório é distribuído sob a licença MIT. O texto
  completo está no arquivo [`LICENSE`](LICENSE).
- **Materiais de terceiros:** os itens listados na
  [seção 14](#14-créditos-de-terceiros) (Leaflet, tiles e dados do OpenStreetMap, Google
  Fonts e dependências Python) não são cobertos pela licença MIT deste repositório e
  continuam sujeitos às suas respectivas licenças.
