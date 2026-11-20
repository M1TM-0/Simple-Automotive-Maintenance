# PENDENCIAS-API.md — contrato adotado, campos sem coluna e decisões pendentes

> **Contrato definitivo (17/11/2026, BE-072).** O backend (`../backend/`, Fases 0–5) implementa
> todos os endpoints da §3, inclusive os de admin (Fase 5, sem tela). A especificação completa está no OpenAPI
> (`/api/docs/` com DEBUG) e na seção 8 de `backlog/backlog_backend.md`. Divergências continuam se
> resolvendo **só em `js/api.js`** (rotas) e nos normalizadores `normChat`, `normMsg`, `normPromo`,
> `normWorkshop`, `normWAtt`. O que mudou na integração está nas §8 e §9.

## 1. Como ligar

`js/config.js`: `API_BASE` (origem, sem barra final) e `DRIVER`.

| DRIVER | Comportamento |
|---|---|
| `local` | login/registro/sessão, veículos + histórico manual e conversas do cliente ficam no `localStorage`. **Todo o resto responde `API_UNAVAILABLE`** e a tela mostra "O servidor ainda não está disponível" (sem dado fictício). |
| `http` (padrão) | tudo pela API. `API_BASE` vazio → `API_UNAVAILABLE`. Sirva o frontend em http://localhost:5500 (origem liberada no CORS do backend). |
| `http` em produção | mesma origem atrás do Nginx: `deploy/nginx/config.prod.js` define `API_BASE: window.location.origin` (sem CORS; cookies de sessão/CSRF `Secure`). CSP em `deploy/nginx/snippets/csp-frontend.conf` (BE-089). |

## 2. Convenções que o frontend assume

- Prefixo `/api/`, JSON `snake_case`. Datas ISO‑8601 com fuso (exibidas no fuso local). Dinheiro como string decimal ou número.
- **Toda entidade devolve `id`** (chave primária) além dos nomes de coluna (`id_workshop`, `id_vehicle`…). `REVIEW.id` é UUID. As telas usam `x.id`.
- Listas: `{count,next,previous,results}` (DRF) ou array simples; paginação por `?page=`. Catálogos pequenos (categorias, serviços, horários, produtos, atendimentos e avaliações da oficina, clientes) são lidos em **todas** as páginas.
- Erros: `400 {campo:[msg]}` ou `{detail}`; `401` → `login.html?next=`; `403` → `404.html?code=403` (exceto histórico, que mostra mensagem); `409` conflito; `404`.
- **P8 sessão/CSRF**: cookie de sessão + header `X-CSRFToken` lido do cookie `csrftoken`. O 1º `POST` da página faz antes um `GET /auth/me/` silencioso para o cookie existir: **o backend precisa definir `csrftoken` em respostas de `GET`** (ex.: `ensure_csrf_cookie`), mesmo em `401`. Trocar por token = só `api.js`.
- **Leitura pública (visitante)**: `GET /service-categories/`, `/services/`, `/map/points/`, `/map/external-points/`, `/promotions/`, `/workshops/{id}/…` não podem exigir login (mapa, home e perfil são públicos). O contrato original marcava catálogo como "C O".
- `GET /auth/me/` → `{user:{id,role,name,email,phone_number?,photo_profile?,status?,setup_complete?}}` (T16 usa nome, telefone, foto, status).
- Fotos por `multipart/form-data`. Para **limpar** uma foto/imagem envia-se o campo vazio (`photo_2=`, `photo_profile=`, `image=`). No veículo as 3 posições são fixas (`photo_1..3`), a interface não "desloca" fotos.

## 3. Endpoints consumidos (todos implementados; admin na Fase 5)

| Área | Endpoint | Observações do que a tela envia/espera |
|---|---|---|
| Auth | `POST /auth/register/` | `{role:'client'\|'workshop', name \| name_fantasy+name_responsible+cnpj(14 dígitos), email, password, phone_number?}` → `201 {user}` |
| | `POST /auth/login/` | `{role,email,password}` (P9: mesmo e-mail pode ser cliente e oficina). `400/401` → "E-mail ou senha incorretos."; `403` com `detail` (conta bloqueada/inativa) é exibido |
| | `POST /auth/logout/`, `GET /auth/me/` | |
| | `POST /auth/password-reset/` `{role,email}` · `POST /auth/password-reset/confirm/` `{token,password}` | `404` não revela se o e-mail existe. **Não há tabela de tokens no banco** |
| Conta | `PATCH /me/` (JSON ou multipart `name, phone_number, photo_profile`) · `POST /me/password/` `{current_password,new_password}` | |
| Catálogo | `GET /service-categories/` · `GET /services/?q=&category=` | itens com `id`, `name`, `id_service_category` (ou `id_category`) |
| Mapa | `GET /map/points/?q=&category=&type=&lat=&lng=&radius_km=&open_now=` | `{kind:'workshop'\|'poi', id, name, type, lat, lng, address, distance_km?, rating_avg?, rating_count?, is_open_now?}` — `category` = id ou nome; `radius_km` padrão 10, máximo 100 (acima → 400); página de 100 itens |
| Mapa (OSM, BE-094) | `GET /map/external-points/?south=&west=&north=&east=` | **não paginado**, sempre 200: `{status:'ok'\|'partial'\|'unavailable'\|'too_large'\|'disabled', detail, source, attribution, license, license_url, count, results:[{id:'osm:<tipo>:<id>', osm_type, osm_id, name, has_name, type, osm_tag, lat, lng, address, osm_url}]}` — estabelecimentos do OpenStreetMap (Overpass) **não cadastrados** no SAM, só exibição; caixa inválida → 400; `api.map.external` (quiet) |
| Home | `GET /promotions/?active=true` | `{id, kind:'promotion'\|'advertisement', title, image_url, workshop:{id,name_fantasy}, type_discount, discount_value, date_end, is_valid_now, is_running_now}` |
| Oficina pública | `GET /workshops/{id}/` | `name_fantasy, phone_number, description, photo_profile, photo_banner, address, latitude, longitude, type` (planos **ou** em `page`/`point`), `operation_hours[{day_of_week,opening_time,closing_time}]`, `services[{id,name,description,price_base,duration_estimate,category_name,disponibility}]`, `rating_avg, rating_count, is_favorite?`, `is_open_now?`, `gallery?` (só então há aba Galeria) |
| | `GET /workshops/{id}/products/` · `/promotions/` · `/reviews/` | avaliações `published`: `{id(uuid),rating,comment,date_creation,workshop_response,date_response,client_name}`; produtos só `active`; promoções só vigentes |
| Favoritos | `GET/POST /favorites/` `{id_workshop}` · `DELETE /favorites/{id_workshop}/` | item: `{id\|id_workshop, name_fantasy, photo_profile, rating_avg, type}` (ou aninhado em `workshop`) |
| Veículos | `GET/POST /vehicles/` · `GET/PATCH/DELETE /vehicles/{id}/` | multipart: `brand, model, year_fabrication, year_model, plate (sem hífen), fuel, exchange, version?, motorization?, color(≤20)?, information?, photo_1..3, mileage_km`; `DELETE` → `409` se houver histórico/atendimento |
| | `GET/POST /vehicles/{id}/history/` | leitura = `vw_vehicle_maintenance_history` (`record_type, description, quantity, unit_price, date_maintenance, mileage_km, observations, interval_km, id_workshop?`); `POST` `{service_name, id_service?, date_maintenance, mileage_km?, observations?, interval_km?}`; **sem PATCH/DELETE** |
| | `GET /vehicles/{id}/upcoming-maintenance/` (BE-077) | `api.vehicles.upcoming(id)`: próximas manutenções **calculadas pelo servidor** `[{id, id_service, service_name, last_date, last_mileage_km, interval_km, next_mileage_km, current_mileage_km, remaining_km, progress_percent, status: ok\|soon\|overdue, reminder_sent_at}]`, mais urgente primeiro. A rotina `jobs` avisa o cliente (sino) uma vez por ciclo quando o item fica `soon`/`overdue` |
| Atendimento (C) | `POST /attendances/` `{id_workshop,id_vehicle,mileage_km?,observations?}` · `GET /attendances/?status=a,b,c&vehicle=` · `GET /attendances/{id}/` · `POST /attendances/{id}/cancel/` | `status` aceita **lista separada por vírgula**. Detalhe: `workshop{id,name_fantasy}`, `vehicle{…}`, `budgets[{id,status_budget,date_validity,observations,total_price,items[{id,item_type,description,quantity,unit_price,subtotal?,id_service_item?,execution_status}]}]` (ou só `budget`), `review?{rating,comment,workshop_response}` |
| Orçamento (C) | `POST /budgets/{id}/approve/` · `/reject/` | |
| Avaliação | `POST /reviews/` `{id_budget,rating,comment?}` (`409` se já avaliado) | |
| Denúncia | `POST /denunciations/` `{target_type,target_id,reason,description?}` (`409` = já denunciado em aberto) | |
| Chat | `GET /chats/` · `POST /chats/{id_workshop}/open/` · `GET /chats/{id}/` · `GET/POST /chats/{id}/messages/` (`?after=<date_sent>`) · `POST /chats/{id}/read/` | chat: `{id, workshop{id,name_fantasy,photo_profile} \| client{id,name}, last_message{content,date_sent}, unread_count, open_attendance{id,status_attendance}?}` — **o servidor envia só o interlocutor**. Mensagem: `{id,content,date_sent,status_message,sender:'client'\|'workshop'}` |
| Notificações | `GET /notifications/?unread=true` · `POST /notifications/{id}/read/` · `POST /notifications/read-all/` · `GET /notifications/unread-count/` | `{id,title,message,date_creation,read_status,url?}`; **`url` só é seguido se for página `.html` do projeto**. Quem cria notificações é o backend |
| Oficina: conta | `GET/PATCH /workshop/me/` | `{id,name_fantasy,name_responsible,email,phone_number,cnpj,status,setup_complete,point{id,name,type,address,latitude,longitude}\|null,page{description,photo_profile,photo_banner}}` |
| | `PATCH /workshop/page/` (multipart) · `GET/PUT /workshop/operation-hours/` · `GET /points-of-interest/?q=` · `POST /workshop/point/` | `PUT` substitui a lista (sem sobreposição; 08–12 e 12–18 são válidos). `POST /workshop/point/`: `{id_point_of_interest}` ou criar `{name,type,latitude,longitude,address}` (se não aceitar, a tela avisa e segue sem ponto — P4) |
| Oficina: catálogo | `GET/POST /workshop/services/` · `PATCH /workshop/services/{id}/` | item: `{id,id_service?,name,name_local?,description_local?,id_service_category,category_name,price_base,duration_estimate,disponibility,status_solicitation?,motivation_rejection?}` |
| | `GET/POST /workshop/products/` · `PATCH /workshop/products/{id}/` (multipart; booleans `true/false`) | `{id,name,description,category,brand,price,disponibility,active,photo}` |
| Oficina: atendimento | `GET /workshop/attendances/?status=` · `GET/PATCH /workshop/attendances/{id}/` · `POST /workshop/attendances/{id}/transition/` `{status}` | detalhe com `client{id,name,phone_number?}`, `vehicle`, `budgets`; `PATCH {mileage_km?,observations?}` |
| Oficina: orçamento | `POST /workshop/attendances/{id}/budget/` · `PATCH /workshop/budgets/{id}/` `{date_validity,observations}` · `POST/PATCH/DELETE /workshop/budgets/{id}/items/{item?}/` · `POST /workshop/budgets/{id}/send/` · `PATCH /workshop/budgets/{id}/items/{item}/execution/` | item: `{item_type,id_workshop_service?,id_product?,id_service_item?,description,quantity(≤3 casas),unit_price}`. **O total exibido é sempre o `total_price` devolvido** |
| Oficina: divulgação | `GET/POST /workshop/promotions/` · `PATCH /workshop/promotions/{id}/` (multipart) | `title,description,id_workshop_service\|id_product (vazio no outro),type_discount,discount_value,date_start,date_end,image,status_promotion('active'\|'inactive')`; resposta traz `effective_status`, `is_valid_now`, `target_name?` |
| | `GET/POST /workshop/promotions/{id}/advertisements/` (multipart `image,date_start,date_end`) | resposta: `advertising_price, payment_status, status_advertisement, is_running_now` |
| Oficina: relacionamento | `GET /workshop/reviews/` · `POST /workshop/reviews/{id}/response/` `{workshop_response}` | todas as avaliações (inclui `hidden`/`under_review`) |
| | `GET /workshop/clients/` · `GET /workshop/clients/{id}/vehicles/` · `GET /workshop/vehicles/{id}/history/` | cliente: `{id,name,attendance_count,last_attendance,vehicles[{id,brand,model,plate}]}`; veículos com `attendances[{id,date_attendance,status_attendance}]`; histórico → `403` se o cliente não autorizou |
| Admin (sem tela, ver P5) | `GET /admin/denunciations/` (`?status=`, `?target_type=`) · `PATCH /admin/denunciations/{id}/` `{status_denunciation, moderation_decision}` · `POST /admin/reviews/{id}/hide/` · `GET /admin/service-requests/` (`?status=`; padrão: pendentes) · `POST …/{id}/approve/` `{id_category?,name?,description?}` · `POST …/{id}/reject/` `{motivation}` | **implementados (Fase 5, BE-073/BE-074), sem tela**; os métodos `api.admin.*` já batem com as rotas e corpos. Só usuário Django `is_staff` (entra por `/admin/`) |

## 4. Campos sem coluna no `init.sql` (premissas P1–P3)

| Campo | Premissa | Comportamento |
|---|---|---|
| `mileage_km` do veículo | **P1** | o formulário e a ficha mantêm o campo e enviam `mileage_km`; se a API não devolver, o valor some (a ficha e o cartão omitem a km). **PENDENTE no banco.** |
| `history_shared` ("oficinas podem consultar o histórico") | **P2** | a chave existe na ficha; sem `history_shared` na resposta fica **desabilitada** com "Disponível em breve". Hoje `403` do histórico da oficina depende dele. |
| `interval_km` ("próxima troca em km") | **P3** | **Resolvida (BE-013 + BE-077).** O campo vai no registro manual nos dois drivers; "Próximas manutenções" vem de `GET /vehicles/{id}/upcoming-maintenance/` com `DRIVER:'http'` (o destaque usa `status !== 'ok'` da API) e é calculada na tela só com `DRIVER:'local'`. |
| `setup_complete` | — | a oficina é levada ao assistente (T17) enquanto `false`; sem o campo a interface assume concluído. |

## 5. Decisões que dependem do responsável do projeto

- **P4 endereço**: `WORKSHOP` não tem endereço; vem de `POINT_OF_INTEREST`. A oficina pesquisa e **confirma** o ponto (checkbox obrigatório). Criar ponto novo só se `POST /workshop/point/` aceitar. Sem ponto a oficina não aparece no mapa (aviso na tela).
- **P5 admin**: perfil admin **confirmado pela DP-03** = usuário Django `is_staff` (Fase 5). **T27 (moderação de denúncias) e T28 (serviços personalizados) NÃO foram construídas** (F8 condicional): a interface provisória é o Django Admin (`/admin/`: contas, catálogo, pontos, divulgações) e as rotas `/api/admin/*` já existem. `auth.require('admin')`, `HOME.admin` e os métodos `api.admin.*` já existem; falta só a tela. O login público não oferece perfil admin (o admin entra por `/admin/`).
- **P6 pagamento**: não há tela de pagamento. Divulgação nasce `pending`; o admin confirma o pagamento no Django Admin e ela entra no ar no início do período (BE-076, DP-09); "No ar" só quando `is_running_now===true`. Cancelada depois de paga → `payment_status: "refunded"` (marcada para estorno).
- **P8**: sessão por cookie + CSRF (ver §2); trocar por token é só `api.js`.
- **Contraste da marca**: branco sobre `--red` = 3,54:1 e `--red` sobre `--cream` = 2,94:1 (abaixo de AA 4,5:1 em texto pequeno). Não alterei a marca. Uma linha resolve o botão principal: definir `--red-btn` em `css/components.css` (sugestão `#D9291F`, ≈ 4,6:1). Textos vermelhos sobre fundo escuro já usam `--red-ink`.

## 6. Itens não integráveis / lacunas do banco ou do contrato

- **Cancelar orçamento pendente sem cancelar o atendimento**: não há endpoint; não existe esse botão.
- **Etapa "aguardando peça"** (RN08 do backlog) não existe no banco: o stepper tem 5 etapas.
- **Recusa de orçamento**: o contrato não diz para qual `status_attendance` o atendimento volta; a interface só relê o servidor.
- **Observações do atendimento**: `ATTENDANCE.observations` é uma coluna só (pedido do cliente e observações técnicas da oficina compartilham o campo).
- **Galeria da oficina**: sem tabela; a aba só aparece se a API devolver `gallery`/`photos`.
- **Presença ("online agora")**: sem dado; removido. Chat sem cartões (só texto) e sem tempo real além do polling de 5 s.
- **Notificações**: o backend as gera nos eventos de atendimento, orçamento, avaliação e chat (BE-070); a tela segue só `url` de página `.html` do projeto.
- **Geocodificação/localização**: sem coordenadas a interface não inventa posição (mapa neutro + aviso).
- **Leaflet 1.9.4** por CDN (unpkg) com SRI oficial (`sha256-p4Nx…BMY=` e `sha256-20nQ…ZBo=`, conferidos contra o pacote do npm). Sem a biblioteca a lista de oficinas continua funcionando.
- **Foto do veículo no driver local** fica em data-URL no `localStorage` (limite de cota); na API vai por multipart.

## 7. Divergências entre o prompt, o banco e o código

1. Prompt usa `image` no upload de promoção; o banco guarda `image_url` (a resposta traz `image_url`).
2. Banco: `status_budget='cancelled'` e `status_advertisement='cancelled'` (dois "l"), mas `status_attendance='canceled'` (um "l"); `enums.js` cobre as duas grafias do anúncio.
3. A view de histórico expõe `description` (não `service_name`); o `POST` manual usa `service_name`.
4. Critério 3 ("nenhum dado fictício") × T02 ("credencial demonstrativa só no driver local, rotulada"): mantive **apenas** a credencial `demo@sam.app`, visível só com `DRIVER:'local'`.
5. T06 diz `chat.html?id=<oficina>`; a interface abre/obtém a conversa (`POST /chats/{id_workshop}/open/`) e usa o **id do chat** (`chat.html?id=<chat>&ask=…`).
6. T02: a Oficina também respeita `?next=` quando o cadastro está concluído (spec cita só o Cliente).
7. T03: telefone da oficina é opcional (o banco permite nulo).
8. `ui.js`: além de remover `[data-soon]`, exporta `pill` (necessário para recalcular a pílula depois de montar o cabeçalho). `data.js`/`api.js`/`workshop-parts.js`/`components-parts.js`/`attendance-parts.js` são arquivos extras de divisão (limite de ~400 linhas); `api.js` (≈650 linhas) ficou único de propósito: é o contrato inteiro num lugar só.

## 8. Backend da Fase 3 implementado — notas para a integração (BE-072)

Rotas de §3 marcadas como Fase 3 (catálogo, oficina, veículos, atendimento/orçamento, chat, avaliações, denúncias, favoritos e promoções da oficina) **existem** desde 17/11/2026. Diferenças em relação ao que as telas assumem:

| Tela / chamada | O backend faz | Ajuste necessário |
|---|---|---|
| T19 `w-attendance.js` → `PATCH /workshop/attendances/{id}/ {observations}` | Grava em `technical_notes` (DP-13: coluna separada) e **não** sobrescreve `observations` (pedido do cliente). Aceita `observations` como sinônimo; a resposta traz os dois campos. | **Resolvido em `api.js` (BE-072):** `normWAtt` entrega à tela `observations = technical_notes` (ou o pedido do cliente enquanto não houver notas) e o pedido original em `client_observations`. |
| T20 `w-budget.js` → `POST/PATCH /workshop/budgets/{b}/items/` | Item no nível raiz (`x.id` funciona) + `budget{id,status_budget,total_price}`. | Nenhum (pode usar `x.budget.total_price` em vez de reler o atendimento). |
| T20 → orçamento enviado | Depois do envio (atendimento `waiting_approval`) itens, validade e observações → **409**. | Nenhum (a tela já não edita após o envio). |
| T07 `chat.js` → `GET /chats/{id}/messages/` sem `after` | Página 1 = mensagens **mais recentes**, em ordem cronológica (página 2 = mais antigas). Mensagem traz `sender` e `mine`. | Nenhum. Para "carregar anteriores", usar `?page=2…`. |
| T07 → `POST /chats/{id_workshop}/open/` | 201 quando cria, 200 quando já existia. Oficina recebe `client{id,name,photo_profile}`. | Nenhum. |
| T12 histórico | `id` é texto (`service-12`, `part-5`) e há `workshop_name`. | Nenhum. |
| T06/T15 favoritos | `id` = `id_workshop` (usado no `DELETE`); `POST` repetido → 200 com o mesmo item. | Nenhum. |
| T24 promoções | Upload em `image`, leitura em `image_url`; `id_workshop_service`/`id_product` vazios = sem alvo. | Nenhum. |
| Listas públicas (`/workshops/{id}/…`, `/map/points/`, `/promotions/`) e notificações | Implementadas na Fase 4 (BE-065…BE-070), ver §9. | Nenhum. |

## 9. Fase 4 — APIs públicas e notificações (BE-065…BE-072)

| Tela / chamada | O backend faz | Observação |
|---|---|---|
| T06 `GET /workshops/{id}/` | Campos **planos** (`description`, `photo_*`, `address`, `latitude`, `longitude`, `type`), `operation_hours`, `services` (disponíveis; personalizados pendentes entram), `rating_avg`/`rating_count` (só `published`), `is_favorite` (`null` sem sessão de cliente), `is_open_now` (fuso do negócio; `null` sem horários). Sem CNPJ, e-mail nem responsável. Oficina inativa, bloqueada ou sem cadastro concluído → 404. Sem `gallery` (DP-20). | A tela já usa `is_open_now` do servidor quando é booleano. |
| T05 `GET /map/points/` | Oficina com ponto e pública → `workshop`; ponto sem oficina → `poi` (ponto vinculado nunca duplica). POI não traz `rating_*` nem `is_open_now`; oficina sem horários não traz `is_open_now`. `category`/`open_now` excluem POIs. | `map.js` envia `category` = id da categoria (aceito). |
| T01/T05 `GET /promotions/?active=true` | Divulgações em execução (`kind:'advertisement'`, `id` = divulgação, `id_promotion`, imagem da divulgação) primeiro; depois promoções vigentes por término. `is_running_now` é `null` em promoção. Cache 30 s. | `normPromo` trata `null` como válido. |
| T06 `GET /workshops/{id}/promotions/` | Só `kind:'promotion'`, mesma forma. | — |
| T08/C01 notificações | `GET /notifications/?unread=true`, `GET /notifications/unread-count/` → `{count}`, `POST …/{id}/read/` e `…/read-all/` → 204. Destinos: cliente `attendance.html?id=`, oficina `w-attendance.html?id=` / `w-reviews.html` / `w-services.html`, ambos `chat.html?id=<chat>`. Chat: 1 notificação por conversa até ler; abrir a conversa (`POST /chats/{id}/read/`) a marca como lida. | — |
| T02 credencial demo | — | **Corrigido (FE-11):** `.demo{display:grid}` vencia o atributo `hidden`; `css/auth.css` ganhou `.demo[hidden]{display:none}`. Com `DRIVER:'http'` a credencial não aparece. |

Verificação de BE-072 (17/11/2026): backend num banco descartável carregado pelos próprios endpoints e 34 telas/estados percorridos no Chromium headless — visitante (T01–T06), cliente (T01, T05–T08, T10–T16), oficina (T07, T08, T18–T26) e oficina no assistente (T17) — sem "O servidor ainda não está disponível", sem "Não foi possível carregar", sem resposta da API ≥ 400 e sem erro de console. Não há `fetch(` fora de `js/api.js`.

## 10. Fase 6 — o que muda para o frontend (BE-081, BE-082, BE-086)

Nenhum arquivo do frontend foi alterado. O contrato agora é verificado automaticamente: `backend/tests/contract/` roda os normalizadores **reais** deste `api.js` (`normChat`, `normMsg`, `normPromo`, `normWorkshop`, `normWAtt`) sobre respostas reais, e `backend/tests/e2e/` percorre F1–F8 no Chromium com este frontend (só `js/config.js` é reescrito para apontar para a API do teste). Mudou `api.js`/tela? Rode `pytest -m e2e` e o teste de contrato.

| Ponto | Comportamento da API | Efeito na tela |
|---|---|---|
| Limites de texto (DP-19) | O servidor impõe os `maxlength` das telas (mensagem 2000, pedido/notas 1000, avaliação 500, denúncia 500, resposta 1000, informações do veículo 600, histórico manual **200**, busca 100) → 400 no campo. Campos sem `maxlength` na tela (descrição de promoção/produto, observações do orçamento) têm limite 1000 no servidor. | Erro 400 aparece sob o campo, como os demais. |
| Corpo grande | JSON > 1 MB ou multipart > 16 MB → **413** `{detail}` (com CORS). | `norm()` mostra o `detail`. |
| Responder o mesmo orçamento duas vezes | 2º clique em aprovar/recusar → **409** "Este orçamento já foi aprovado/recusado." (antes 200 e nova notificação à oficina). | A confirmação mostra o erro. |
| Schema (só documentação) | `/workshop/operation-hours/` documentado como paginado (a resposta sempre foi `{count,…,results}`); `user` do login/cadastro/me sem `name_fantasy`/`name_responsible` para cliente; chat traz `workshop` **ou** `client`. Parâmetros de caminho: `{id_vehicle}`, `{id_budget}`, `{id_budget_item}`, `{id_client}` (P-22). | Nenhum (as rotas são as mesmas). |

## 11. Fase 7 — produção (BE-088…BE-093)

- **Mesma origem**: em produção o Nginx serve o frontend e repassa `/api/`, `/admin/`, `/static/` e `/media/` à API (DP-21). `js/config.js` é substituído na imagem por `deploy/nginx/config.prod.js` (`API_BASE = window.location.origin`); o `api.js` não mudou. URLs de imagem chegam absolutas e na mesma origem (`https://<domínio>/media/…`).
- **CSP** (`deploy/nginx/snippets/csp-frontend.conf`): scripts só do próprio site e do `unpkg.com` (Leaflet com SRI); estilos também do Google Fonts; imagens do próprio site, `data:`, `blob:` e dos tiles do OSM; `connect-src 'self'`. Verificado no Chromium em 27 telas/estados com CORS desligado (`backend/tests/e2e/test_same_origin_csp.py`): nenhuma violação.
- **Uploads**: o Nginx aceita até 17 MB e responde 413 em JSON (`{"detail": …}`) acima disso; até 16 MB quem responde é a API (limites da Fase 6).
- **Tiles do mapa (pendente, DP-22/FE-10)**: `tile.openstreetmap.org` não é para produção com tráfego; ao trocar o provedor, atualize `js/map.js`, a atribuição e o `img-src` da CSP.
- Rota nova de infraestrutura, não consumida pelas telas: `GET /api/health/jobs/` (batimento da rotina de expiração, para monitor externo).
