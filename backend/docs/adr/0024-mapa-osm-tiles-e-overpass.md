# ADR 0024 — Mapa: tiles do OpenStreetMap e estabelecimentos externos pela Overpass

- **Status:** Aceito (decisão do responsável no BE-094, 2026-11-18). Substitui a parte
  "Tiles do mapa: PENDENTE" do ADR 0022 e a parte "escolher a fonte" do ADR 0010.
- **Tarefas:** BE-094 (mapa, pontos de interesse)

## Contexto

O mapa (T05, Leaflet) usava os tiles públicos do OSM sem decisão formal e só mostrava as
oficinas do SAM e os pontos importados por arquivo (`import_pois`). O responsável decidiu:
sem serviço pago, sem domínio público, sem infraestrutura geográfica própria.

## Decisão

**Tiles**
- Provedor: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, atribuição
  "© OpenStreetMap contributors" (controle do Leaflet + legenda abaixo do mapa).
- Substituível por configuração: `SAM.config.MAP_TILES = { url, attribution, maxZoom }`
  (`frontend/js/config.js` ou `deploy/nginx/config.prod.js`) + host em `img-src` da CSP.
- Política de uso do OSM: atribuição visível; **Referer válido** — a página manda
  `Referrer-Policy: same-origin` (Nginx/Django), então a camada de tiles usa
  `referrerPolicy: 'strict-origin-when-cross-origin'` (só a origem vai no Referer; sem ele
  o OSM devolve um tile de bloqueio); cache HTTP do navegador intacto (nenhum proxy de
  tiles, nenhum `no-cache`); sem pré-carga nem download em massa (só a área visível que o
  Leaflet pede).

**Pontos de interesse: duas fontes complementares**
1. **SAM** (inalterado): `GET /api/map/points/` — oficinas cadastradas (perfil, chat,
   favorito, atendimento, avaliação) e pontos importados por `import_pois`.
2. **OpenStreetMap pela Overpass API** (novo): `GET /api/map/external-points/?south=&
   west=&north=&east=` (`apps/workshops/overpass.py`). Etiquetas: `amenity=fuel`,
   `shop=car_repair`, `shop=tyres`, `shop=repair`, `shop=car_parts`, `amenity=car_wash`.
   - Só a região visível e só com zoom ≥ 13 no frontend; no servidor, a caixa é coberta
     por células de 0,05° e acima de 16 células responde `too_large` sem consultar.
   - Cache por célula no cache do Django (24 h; `DatabaseCache` compartilhado em
     produção); só as células que faltam vão numa única consulta.
   - Orçamento global de consultas por minuto (10), recuo exponencial depois de falha,
     429 ou 5xx (60 s → 15 min), tempo limite (12 s) e resposta limitada a 5 MB.
   - **Sempre HTTP 200** com `status` `ok|partial|unavailable|too_large|disabled`: a
     falha da Overpass nunca afeta `/api/map/points/` nem o resto do mapa.
   - Duplicatas evidentes removidas no servidor: mesmo id do OSM num ponto importado
     (`external_id` `node/123` ou `n123`), mesmo lugar (≤ 5 m) ou nome parecido a até
     100 m de um ponto do SAM.
   - No mapa: losango âmbar menor (forma e tamanho diferentes do pino do SAM), popup com
     tipo, endereço, "não cadastrado no SAM" e link para o OSM — **sem** perfil, chat,
     favorito ou solicitação. Fora da lista lateral (que é só do SAM).
   - Limite por IP no endpoint (`THROTTLE_EXTERNAL_MAP`, 60/min).
- Instância configurável (`SAM_OVERPASS_URL`; vazio desliga). Padrão: a pública
  `overpass-api.de`.

**Licença (ODbL 1.0)**: os dados vêm do OSM a cada consulta e ficam só no cache (nome,
tipo, posição, endereço, id); nada é gravado nas tabelas do SAM nem redistribuído como
base. Atribuição visível no mapa, na legenda, em cada popup e na resposta da API
(`attribution`, `license`, `license_url`).

## Consequências

- Sem custo e sem infraestrutura nova; o mapa funciona inteiro sem a Overpass.
- A Overpass pública é compartilhada e às vezes fica sem capacidade (no dia da validação,
  `overpass-api.de` e outras instâncias responderam 502/504 ou estouraram o tempo): o
  usuário vê o aviso e só as oficinas do SAM. Para uso maior: instância própria da
  Overpass (fora do escopo) ou outra pública via `SAM_OVERPASS_URL`.
- O servidor concentra as consultas num só IP; por isso cache, orçamento e recuo.
- `shop=repair` é genérico (pode incluir reparo de eletrônicos); mantido por decisão e
  rotulado "Outro"/"Reparos".
