# Lista de verificação — endpoint novo (BE-084)

Use na revisão de todo PR que cria ou altera uma rota da API. Os itens marcados com
**(automático)** são cobrados pela suíte `tests/security/test_authz_matrix.py`; os
demais dependem de quem revisa.

## Autorização

- [ ] **(automático)** A rota está na matriz `CONTRACT` (seção 8 do backlog) com a política
      certa: `public`, `authenticated`, `account`, `client`, `workshop` (assistente T17),
      `workshop_ready` (demais `/workshop/*`) ou `admin`.
- [ ] **(automático)** `permission_classes` declarada na view e coerente com a matriz:
      visitante → 401 com `WWW-Authenticate: Session`; perfil errado → 403 com `{detail}`.
- [ ] Rotas `/workshop/*` usam `WORKSHOP_PERMISSIONS` (fora do assistente) — há teste que
      percorre o URLconf.
- [ ] Rotas `/api/admin/*` herdam `AdminViewMixin` (auditoria em `sam.audit`) — há teste que
      percorre o URLconf.
- [ ] **(automático)** O queryset é filtrado pelo `request.user` **antes** de buscar o
      objeto: recurso de outro dono → 404 (nunca 403, nunca 400 de validação antes do 404).
      Prefira `OwnedByClientMixin`/`OwnedByWorkshopMixin` ou `get_object_or_404(..., <dono>=request.user.id)`.
- [ ] **(automático)** Parâmetro de caminho com nome `id_<entidade>` (ou `{id}` sob um
      segmento conhecido). Nome novo → acrescente a entidade em `ENTITY_BY_PARAM` e em
      `Side.entity` (`apps/core/tests/world.py`); alvo público (não é recurso do dono) →
      `TARGET_PARAMS`.
- [ ] Filtros por perfil usam **perfil e id** juntos (cliente e oficina têm sequências de id
      próprias: o id 7 existe nas duas tabelas). Ver `TestRoleConfusion`.

## Dados e corpo da requisição

- [ ] **(automático)** O corpo não aceita `id_client`, `id_workshop` (exceto alvo escolhido),
      `status*` (exceto ação explícita), `total_price`, `advertising_price`, `payment_status`,
      `password_hash`, `email`/`cnpj` (exceto cadastro/login). Exceção → `REQUEST_FIELD_ALLOWLIST`
      com justificativa.
- [ ] Serializer de escrita com lista explícita de campos e limites (`apps/core/limits.py`).
- [ ] **(automático)** Resposta sem dado privado de outro dono; resposta pública sem CNPJ,
      e-mail, responsável, conteúdo inativo/oculto (marcador `SEGREDO-*` do mundo de teste).

## Contrato e documentação

- [ ] `@extend_schema` com `request`, `responses` (inclusive 401/403/404/409) e `summary`.
- [ ] `spectacular --validate --fail-on-warn` limpo; `get_queryset` que lê `request.user`
      usa `is_schema_generation(self)`.
- [ ] Teste de contrato (`tests/contract/`) exercita a rota com resposta 2xx validada pelo schema.
- [ ] Rota consumida pelo frontend: `frontend/js/api.js` e `frontend/PENDENCIAS-API.md`.

## Banco

- [ ] Escrita em serviço com `@transactional`; erro do banco traduzido por `db_errors`
      (409 com a mensagem do banco).
- [ ] Sem `raw()`, `extra()`, `RawSQL` nem SQL montado com f-string/`%`/`format` (há teste e regra
      do ruff).

## Integração externa (BE-094)

- [ ] Chamada a serviço de terceiros (ex.: Overpass em `apps/workshops/overpass.py`) com
      tempo limite, resposta limitada em bytes, esquema de URL conferido, cache, orçamento
      de chamadas e recuo depois de falha; a falha **não** vira 5xx nem derruba outra
      funcionalidade (responda 200 com um `status`, como `/map/external-points/`).
- [ ] Testes nunca chamam o serviço público: simule com um servidor HTTP local
      (`apps/workshops/tests/test_overpass.py::FakeOverpass`) e desligue a URL em
      `config/settings/test.py`.
- [ ] Rota com parâmetros obrigatórios na query string: acrescente-os em `QUERY` de
      `tests/perf/test_query_counts.py` (o detector de N+1 chama cada GET).
