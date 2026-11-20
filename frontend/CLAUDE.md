# CLAUDE.md — SAM (Simple Automotive Maintenance)

Frontend do SAM, plataforma que conecta donos de veículos (Cliente) a oficinas e mecânicos (Oficina). Slogan: "Your car • Your care".
Esta pasta tem o frontend (HTML5 + CSS3 + JavaScript puro), sem dados fictícios. Fala com o backend (`../backend/`: Django + DRF + PostgreSQL, Fases 0–7 prontas) **só por `js/api.js`**, com `DRIVER:'http'` (padrão). Sem servidor, `DRIVER:'local'` mantém login, veículos e conversas do cliente no `localStorage`.

## Comandos
- Rodar: backend na porta 8000 (`docker compose up` na raiz) e `python -m http.server 5500` nesta pasta → http://localhost:5500/ (origem liberada no CORS). `js/config.js`: `API_BASE`, `DRIVER` (`'http'` padrão; `'local'` sem servidor).
- Produção (BE-089): o Nginx serve esta pasta e a API na **mesma origem**; a imagem troca `js/config.js` por `../deploy/nginx/config.prod.js` (`API_BASE: window.location.origin`). Não altere a lógica do `api.js` para isso.
- Não há build nem bundler. Validar sintaxe: `node --check js/*.js`.
- Zerar dados locais: `localStorage.clear()`. Fontes do Google Fonts (fallback Georgia/system-ui). Mapa: Leaflet 1.9.4 por CDN com SRI (única biblioteca externa).
- Mapa (BE-094, ADR 0024): tiles do OSM público (provedor trocável por `SAM.config.MAP_TILES` + CSP), camada com `referrerPolicy: 'strict-origin-when-cross-origin'` (a política do OSM exige Referer; a página usa `same-origin`). Duas fontes: SAM (`api.map.points`, pino em gota, lista lateral) e OpenStreetMap (`api.map.external`, só com zoom ≥ 13, losango âmbar, popup com link para o OSM e **sem** perfil/chat/favorito/solicitação). Falha da Overpass → aviso em `#extst`; o resto do mapa não muda.

## Regras técnicas (não quebrar sem pedir)
- Sem frameworks, build, TypeScript nem **ES modules**: abre por duplo clique (file://). Scripts clássicos + namespace global `window.SAM`.
- **Toda chamada de dados passa por `js/api.js`** (nunca `fetch` na página). Contrato definitivo (implementado no backend) em `PENDENCIAS-API.md`; divergência se resolve em `api.js` (rotas e normalizadores). Regras de negócio ficam no backend: a interface valida formato/obrigatoriedade e **exibe a mensagem de erro da API**.
- Domínios novos (oficina, atendimentos, orçamentos, favoritos, notificações, denúncias, avaliações) são **só HTTP**: com `DRIVER:'local'` respondem `API_UNAVAILABLE`. **Nunca fabrique dados locais para eles.**
- HTML semântico, `aria-current` na navegação, `role=tablist` (setas alternam), modais com `role=dialog`+`aria-modal`+foco preso+Esc, `aria-live` em listas, `role=alert` nos erros de campo, foco visível, teclado completo. Botão só com ícone leva `aria-label` e `title`.
- Todo texto dinâmico em template literal passa por `esc()`; URL de imagem da API por `ui.url()`.
- **CSP de produção** (`../deploy/nginx/snippets/csp-frontend.conf`): nada de `<script>` inline, `on*=` em HTML/template, `eval`/`new Function` nem `fetch` para outra origem. Scripts só de `'self'` e `unpkg.com` (Leaflet); estilos de `'self'`, Google Fonts e `unpkg.com` (`style=""` é permitido); imagens de `'self'`, `data:`, `blob:` e tiles do OSM. Origem externa nova = atualizar a CSP no mesmo commit; `backend/tests/e2e/test_same_origin_csp.py` reprova qualquer violação.
- Sem `!important`, exceto no reset de `prefers-reduced-motion`. Animar só `transform`/`opacity` (150–450 ms, `var(--ease)`).
- Estilo compartilhado vai em `css/components.css`; estilo de uma página só, no CSS dela. Só tokens (nunca cor fixa). Texto vermelho usa `--red-ink`.
- Formulários: `novalidate`, `form.wire()` (sem duplo envio, botão "…ando"), mensagem sob o campo (`.err#e-<campo>`), foco no primeiro inválido, erros 400 da API mapeados pelo nome do campo. Dinheiro em **centavos inteiros** (`fm.cents`, `fm.sub`), nunca `float` para somar.
- Textos pt-BR; identificadores em inglês; navegação em inglês (HOME, MAP, CHAT, VEHICLE · ATTENDANCE, SHOP). Datas dd/mm/aaaa (`fm.date`, converte o fuso), moeda `brl`, km `km`.
- Rótulos dos enums do banco só em `js/enums.js` (`SAM.lbl`, `SAM.opts`).

## Estrutura
```
*.html  (um por tela, ver README.md)   404.html
css/    base.css components.css + um por página/área (home map shop chat vehicles auth attendance workshop notifications)
js/     ui.js config.js enums.js auth.js data.js api.js components.js components-parts.js
        attendance-parts.js workshop-parts.js (só nas telas que usam) + um .js por página
```
- **Ordem dos scripts**: `ui.js` → `config.js` → `enums.js` → `auth.js` → `data.js` → `api.js` → `components.js` → `components-parts.js` → (`attendance-parts.js`, `workshop-parts.js`) → `<pagina>.js`. (Em `map.html` o Leaflet vem antes de `ui.js`.)
- Cabeçalho (C01) é montado por `components.js` em `<header class="hdr" id="hdr">` (mesmo HTML/classes de sempre) e muda por perfil; menu do usuário e sino com contador (poll 60 s).
- `SAM` (global): `ui.js` → `$ $$ esc fmt brl km now toast car I reveal pill`; `config`; `enums.js` → `enums lbl list opts STEPPER STEP_OF GROUPS`; `auth` (`user setSession require(role, needSetup) next home role`); `data.js` → `store save local(vehicles,chats) V convs shops vn …` (driver local); `api` (`auth vehicles chats account catalog map promotions workshops favorites attendances budgets reviews denunciations notifications workshop admin`); `ui` (`load fail loading emptyHtml failHtml url stepper miniStepper badge table subnav tabs modal confirm poll report requestAttendance reviewAttendance promoCard …`); `fm` formatadores; `v` validadores; `form` (`fld wire err apply busy photo pw`); `W` (horários, ponto, serviços da oficina); `att` (helpers de orçamento).
- Padrão de página: IIFE → desestrutura `SAM` → guarda (`SAM.auth.require('client'|'workshop', true)`) → `ui.load(view, () => SAM.api…, draw)` com os 4 estados (carregando, vazio, erro com "Tentar de novo", **API indisponível**).

## Dados e autenticação
- Driver `local`: `localStorage` (prefixo `sam:v1:`; por usuário `u:<id>:vehicles|convs`; globais `accounts`, `session`, `workshops`). A senha local usa PBKDF2 (Web Crypto) e **não é segurança de produção**. Veículos locais são migrados para o formato da API (`year_fabrication`, `fuel`/`exchange` por código, `mileage_km`, `photo_1..3`).
- Driver `http`: sessão por cookie do Django + CSRF (P8); `session` guarda só o cache de "quem sou eu" (id, nome, e-mail, perfil, `setup_complete`).
- **Única exceção de dado de demonstração**: `demo@sam.app` / `demo1234` em `login.js`, visível **só** com `DRIVER:'local'` e rotulada.
- Perfis: `client`, `workshop` (tabelas separadas; o mesmo e-mail pode existir nas duas) e `admin` (previsto, **não confirmado**: T27/T28 não existem).

## Design (mantenha o estilo do protótipo)
```
--cream #EDEADD  fundo        --sand #DCD9C8   painéis/sidebar    --olive #CDCFB2  estampa
--red-deep #B01E26 nav ativa, blocos do título   --red #FF3B2F  CTA, bolhas do cliente, SAM
--ink #1C1C1C  --muted #5A584D  --online #7ED957  --amber #FFA800  --paper #EDEADD (texto sobre vermelho)
```
- Fontes: Poppins (UI) + Playfair Display (título e blocos de etiqueta).
- Formas: cards com raio 16–20px, pills arredondados, nav ativa em "squircle" vermelho-escuro, superfícies planas (sombra só em popups).
- Modo escuro: tokens redefinidos em `prefers-color-scheme` e `[data-theme="dark"]`. Respeite `safe-area-inset-*`.
- Breakpoints: 820px (colunas viram uma) e 640px (nav vira barra inferior).
- Título da home segue a referência: linhas 1 e 2 empilhadas, faixa "YOUR CAR • YOUR CARE" à esquerda, "SAM" ao lado descendo até o subtexto (grid `.tg`).

## Regras de negócio que a interface precisa respeitar
- Dois perfis (Cliente e Oficina). Mapa mostra oficinas cadastradas **e** pontos de interesse não cadastrados (do SAM e do OpenStreetMap), visualmente distintos por forma e cor; atribuição "© OpenStreetMap contributors" (ODbL) sempre visível.
- Catálogo "Shop local" é **só informativo**: sem carrinho, sem pagamento. Compra se negocia pelo chat.
- Promoções têm validade. Orçamento = peças + mão de obra + total; o cliente aprova ou recusa.
- Histórico de manutenção é cumulativo e **nunca é apagado**. O cliente autoriza a oficina a consultá-lo.
- Avaliação só depois do atendimento concluído, uma por atendimento.
- Fora de escopo: pagamento, marketplace, entrega, controle financeiro, site individual por oficina.

## Armadilhas já encontradas
- Seletor genérico como `.conv span` esticou o avatar do chat. Use classes (`.tx`) em vez de seletores de tag.
- Pseudo-elemento absoluto em container com rolagem só cobre a área visível. A estampa do chat é `background ... local` no próprio `.msgs`.
- `display:contents` no `h1` do hero faz as linhas do título virarem itens do grid `.tg`.

## Como adicionar uma página
1. Copie um HTML existente (cabeçalho `#hdr` vazio, links `base.css` + `components.css`, scripts na ordem acima).
2. Crie `js/<pagina>.js` (IIFE, guarda, `ui.load`) e, só se precisar, `css/<pagina>.css`.
3. Dados novos entram em `api.js` (contrato) e são documentados em `PENDENCIAS-API.md`; o item de menu/aba ativo é mapeado em `CUR` (`components.js`).
4. Atualize a tabela do `README.md` e este arquivo.

## Armadilhas (continuação)
- Seletor genérico (`.conv span`) esticou avatar; use classes. Pseudo-elemento absoluto em container com rolagem só cobre a área visível.
- `<input>` tem largura intrínseca: em item de flex dentro de coluna `1fr` use `width:0; flex:1` (ou `minmax(0,1fr)`), senão a página rola na horizontal.
- `input[type=file].sr` precisa de largura 1px explícita (`.fld input` o alarga).
- `e.currentTarget` é `null` depois de um `await`: guarde em uma const antes.
- Um 401 em página pública apagaria a sessão/redirecionaria: leituras públicas usam `quiet` em `api.js`.
- Regra de classe com `display:` vence `[hidden]` (mesma especificidade, folha posterior): declare `.x[hidden]{display:none}` junto (foi o que deixava a credencial demo visível com `DRIVER:'http'`).

## Pendências
Ver `PENDENCIAS-API.md` (contrato adotado, campos sem coluna P1–P3, decisões P4–P8, T27/T28 e divergências).
