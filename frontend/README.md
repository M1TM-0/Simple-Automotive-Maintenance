# SAM — Simple Automotive Maintenance (frontend)

Cada página tem seu HTML, CSS e JS. Navegação por perfil: **Cliente** `HOME MAP CHAT VEHICLE` · **Oficina** `HOME CHAT ATTENDANCE SHOP`.

| Tela | HTML | CSS | JS |
|---|---|---|---|
| T01 Home | index.html | home.css | home.js |
| T02 Login (Cliente/Oficina) | login.html | auth.css | login.js |
| T03 Criar conta | register.html | auth.css | register.js |
| T04 Recuperar senha | forgot-password.html(?token=) | auth.css | forgot-password.js |
| T05 Mapa e busca (Leaflet; SAM + OpenStreetMap, BE-094) | map.html | map.css | map.js |
| T06 Perfil público da oficina | shop.html?id= | shop.css | shop.js |
| T07 Chat (Cliente e Oficina) | chat.html?id= | chat.css | chat.js |
| T08 Notificações | notifications.html | notifications.css | notifications.js |
| T09 Erro 404/403/500 | 404.html?code= | — | error.js |
| T10 Meus veículos | vehicles.html | vehicles.css | vehicles.js |
| T11 Cadastro/edição de veículo | vehicle-new.html(?id=) | vehicles.css | vehicle-new.js |
| T12 Detalhe do veículo + histórico | vehicle.html?id= | vehicles.css | vehicle.js |
| T13 Meus atendimentos | attendances.html | attendance.css | attendances.js |
| T14 Detalhe do atendimento (Cliente) | attendance.html?id= | attendance.css | attendance.js |
| T15 Oficinas favoritas | favorites.html | components.css | favorites.js |
| T16 Minha conta | account.html | auth.css, vehicles.css | account.js |
| T17 Cadastro oficial da oficina | workshop-setup.html | workshop.css | workshop-setup.js |
| T18 Atendimentos da oficina (quadro/lista) | w-attendances.html | attendance.css | w-attendances.js |
| T19 Detalhe do atendimento (Oficina) | w-attendance.html?id= | attendance.css | w-attendance.js |
| T20 Editor de orçamento | w-budget.html?attendance= | attendance.css | w-budget.js |
| T21 Perfil e conta da oficina | w-profile.html | workshop.css | w-profile.js |
| T22 Serviços da oficina | w-services.html | workshop.css | w-services.js |
| T23 Produtos da oficina | w-products.html | workshop.css | w-products.js |
| T24 Promoções e divulgações | w-promotions.html | workshop.css | w-promotions.js |
| T25 Avaliações recebidas (+M04) | w-reviews.html | workshop.css | w-reviews.js |
| T26 Clientes e veículos atendidos | w-clients.html | workshop.css | w-clients.js |
| M01–M03 modais | (abrem nas telas acima) | components.css | attendance-parts.js, components-parts.js |
| T27/T28 Moderação (admin) | **não construídas** (P5 pendente) | — | — |

Compartilhado: `css/base.css` (tokens, nav, botões) e `css/components.css` (modal, tabela responsiva, selos, stepper, abas, estados);
`js/ui.js` (helpers), `config.js`, `enums.js` (rótulos pt-BR do banco), `auth.js`, `data.js` (driver **local**), `api.js` (**única** porta de dados),
`components.js` (cabeçalho por perfil + sino, estados, modal, stepper, tabela, abas, polling) e `components-parts.js` (formatadores, validadores, formulários).

## Como rodar
- **Com a API (padrão)**: `js/config.js` já vem com `DRIVER:'http'` e `API_BASE:'http://localhost:8000'`. Suba o backend (`docker compose up` na raiz, ou `backend/` com `runserver 8000`) e sirva esta pasta na porta **5500** (`python -m http.server 5500` → http://localhost:5500/; é a origem liberada no CORS do backend). Todas as telas falam com a API real (BE-072, verificado no navegador). O contrato definitivo está em `PENDENCIAS-API.md`.
- **Sem servidor** (`DRIVER:'local'`): abra `index.html`. Funcionam cadastro/login, veículos, histórico manual e conversas do cliente (no `localStorage`); as demais telas mostram "O servidor ainda não está disponível" — **não há dados fictícios**. A credencial demonstrativa só aparece neste modo.
- **Produção** (BE-089): o proxy Nginx serve esta pasta e a API na mesma origem (`https://<domínio>/` e `https://<domínio>/api/`), com HTTPS e Content-Security-Policy. A imagem do proxy substitui `js/config.js` por `deploy/nginx/config.prod.js` (`API_BASE` = origem da página). Implantação: `backend/docs/RUNBOOK.md`.
- Zerar dados locais: `localStorage.clear()` no console.
