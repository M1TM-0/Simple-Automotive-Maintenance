# Produção segura (BE-085) e limites de entrada (BE-086)

Decisões tomadas na Fase 6. As settings ficam em `config/settings/prod.py`; os testes
em `tests/security/test_production.py` (inclui `check --deploy` sem avisos) e
`tests/security/test_input_limits.py`.

## HTTPS, cookies e cabeçalhos

| Item | Valor | Por quê |
|---|---|---|
| `DEBUG` | `False` obrigatório | `prod.py` aborta com `True`. |
| `ALLOWED_HOSTS` | lista explícita, sem `*` | `prod.py` aborta se vazio ou com curinga. |
| `SECURE_SSL_REDIRECT` | `True` | HTTP → 301 para HTTPS. Exceção: `^api/health/` (health check do compose/orquestrador na rede interna). |
| `SECURE_PROXY_SSL_HEADER` | só com `USE_X_FORWARDED_PROTO=True` | O Nginx (DP-22, BE-089) termina o TLS e define `X-Forwarded-Proto`. Sem proxy, o cabeçalho não é confiável (testado: continua redirecionando). |
| HSTS | `31536000` s (1 ano) + `includeSubDomains` | Navegador nunca volta a tentar HTTP. |
| HSTS preload | **desligado** por padrão (`security.W021` silenciado só nesse caso) | Entrar na lista de preload dos navegadores leva meses para desfazer; é decisão do dono do domínio. Ligue com `SECURE_HSTS_PRELOAD=True`. |
| Cookies | sessão `Secure` + `HttpOnly` + `SameSite=Lax`; `csrftoken` `Secure` + `SameSite=Lax` | `csrftoken` **não** é `HttpOnly`: o frontend lê o cookie para enviar `X-CSRFToken` (contrato P8). |
| `X-Frame-Options` | `DENY` | Nada do SAM é exibido em iframe. |
| `X-Content-Type-Options` | `nosniff` | API só JSON; impede o navegador de "adivinhar" HTML. |
| `Referrer-Policy` | `same-origin` | Links externos não recebem a URL interna. |
| `Cross-Origin-Opener-Policy` | `same-origin` | Isola a janela de páginas abertas por outros sites. |
| Documentação interativa | `/api/schema/` e `/api/docs/` só para usuário Django `is_staff` fora do `DEBUG` | Útil para a moderação/operação; visitante e contas cliente/oficina recebem 401/403 (testado). |
| E-mail de redefinição | `SAM_EMAIL_ASYNC=True` (thread) | O envio SMTP leva centenas de ms; com envio síncrono o tempo de resposta denunciava que o e-mail existe (limitação registrada na Fase 2). Falha de envio vai para o log `auth.password_reset_email_failed`. Se o worker reiniciar no meio do envio, aquele e-mail se perde — o usuário pede de novo. |

## Proxy reverso (Fase 7, BE-089)

| Item | Valor | Por quê |
|---|---|---|
| CSP do frontend | `deploy/nginx/snippets/csp-frontend.conf` | Scripts só do site e do `unpkg.com` (Leaflet com SRI); `connect-src 'self'`; `frame-ancestors 'none'`; `object-src 'none'`. `'unsafe-inline'` só em `style-src` (atributos `style=""` dos templates). Provada no Chromium em 27 telas sem violação (`tests/e2e/test_same_origin_csp.py`). |
| CSP da API | `default-src 'none'; frame-ancestors 'none'` | Respostas JSON nunca executam nada. Exceção: `/api/docs/` (Swagger, só `is_staff`). |
| Mídia | só `jpg/png/webp`, `nosniff`, CSP `sandbox` | Upload nunca vira página ativa, mesmo aberto direto. |
| TLS | 1.2 e 1.3, ECDHE, sem tickets; SNI desconhecido recusado (`ssl_reject_handshake`) | Mozilla *intermediate*; IP direto ou outro domínio não recebem o site. |
| IP do cliente | Nginx **reescreve** `X-Forwarded-For` com `$remote_addr`; API com `SAM_NUM_PROXIES=1` | Limites de taxa, bloqueio de login e auditoria usam o IP real. |
| Logs de acesso | JSON sem query string (o token de redefinição não vai para o log); 180 dias | Marco Civil da Internet, art. 15. |
| Compressão | só estáticos; respostas da API sem gzip | Evita BREACH em respostas com dados do usuário. |

**Defeito corrigido na Fase 7:** com `NUM_PROXIES` indefinido (padrão do DRF) a API usava
o `X-Forwarded-For` **enviado pelo cliente** como IP — trocando o cabeçalho a cada
tentativa, qualquer um contornava o limite de cadastro (10/min por IP) e o de login por
IP. Agora o padrão é `SAM_NUM_PROXIES=0` (só `REMOTE_ADDR`) e `1` atrás do Nginx
(`tests/security/test_client_ip.py`).

## Limites de entrada (BE-086)

* **Texto** (`apps/core/limits.py`): o limite é o `maxlength` da tela (DP-19). As colunas
  `TEXT` do banco não limitam nada; os serializers usam as constantes e o teste confere
  que a tela tem o mesmo número. Campos sem `maxlength` na tela (descrição de promoção,
  produto, observações do orçamento) usam o limite do servidor (1000) e a tela exibe o
  400 da API no campo.
* **Histórico manual**: 200 caracteres (a tela T12 sempre limitou a 200; o servidor
  aceitava 1000).
* **Senha**: no máximo 128 caracteres (o Argon2 processa a senha inteira; sem teto, uma
  senha de megabytes vira custo de CPU no login).
* **Busca** (`?q=`): no máximo 100 caracteres e sem NUL → 400 em `q`. Antes, `?q=%00` em
  `/api/services/` e `/api/points-of-interest/` dava 500.
* **Corpo**: `RequestSizeLimitMiddleware` responde 413 pelo `Content-Length` — 1 MB para
  JSON (`SAM_MAX_BODY_BYTES`) e 16 MB para multipart (`SAM_MAX_UPLOAD_BYTES` = 3 fotos +
  1 MB). Até 200 campos e 10 arquivos por requisição. Rede de segurança no tratador de
  exceções: `RequestDataTooBig` → 413 e NUL que escape da validação → 400.
* **Datas em query string**: `?after=2026-13-45T99:99` no chat dava 500 (data com formato
  válido e valor impossível); agora 400.
* **SQL**: proibido `raw()`, `extra()`, `RawSQL` e SQL montado com f-string/`%`/`+`/`format`
  (`tests/security/test_sql_safety.py` + regra `S608` do ruff). Exceção consciente leva
  `# sql-safe: <motivo>` na linha.
