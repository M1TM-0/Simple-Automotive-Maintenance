# ADRs do backend SAM

Um ADR por decisão da seção 15 do `backlog/backlog_backend.md` (DP-01…DP-23); 0024–0026 são
as decisões do responsável no BE-094. Na Fase 0
(BE-001) **todas as decisões foram as recomendações do backlog**; o número do ADR é o
número da DP. Status padrão: *Aceito por padrão — recomendação do backlog*. Itens que ainda
dependem do responsável estão marcados **pendente** no próprio ADR e no
`backend/docs/ACEITE.md`.

| ADR | Decisão | Tarefas | Escrito |
|---|---|---|---|
| [0001](0001-init-sql-fonte-do-schema.md) | `init.sql` é a fonte do schema; `core/0001` o aplica uma vez; mudanças por `RunSQL` | BE-001, BE-007, BE-014, BE-091 | Fase 7 |
| [0002](0002-autenticacao-dois-perfis.md) | Sessão Django + CSRF com `Principal` por perfil (sem JWT) | BE-024…BE-031, BE-033 | Fase 7 |
| [0003](0003-perfil-admin.md) | Administração/moderação = usuário Django `is_staff` | BE-035, BE-073…BE-078 | Fase 5 |
| [0004](0004-imagens-em-volume.md) | Imagens em volume atrás de storage abstrato | BE-021, BE-089, BE-090 | Fase 7 |
| [0005](0005-colunas-do-veiculo-e-preventiva.md) | Colunas do veículo, `interval_km` e manutenção preventiva | BE-008, BE-013, BE-077 | Fase 5 |
| [0006](0006-cadastro-concluido.md) | `setup_complete` = ≥ 1 serviço | BE-028 | Fase 7 |
| [0007](0007-historico-para-oficina.md) | Oficina vê o histórico com `history_shared` + atendimento | BE-043, BE-056 | Fase 7 |
| [0008](0008-cancelamento-de-atendimento.md) | Cliente e oficina cancelam até `in_progress`; sem limite de duplicidade | BE-045, BE-047 | Fase 7 |
| [0009](0009-divulgacao-paga.md) | Divulgação paga: preço configurável, pagamento manual | BE-064, BE-076 | Fase 5 |
| [0010](0010-pontos-de-interesse.md) | Pontos de interesse por importação idempotente (fonte: ver 0024) | BE-071 | Fase 7 |
| [0011](0011-notificacoes.md) | Notificações da aplicação, `url` interna, sem e-mail | BE-069, BE-070 | Fase 7 |
| [0012](0012-redefinicao-de-senha.md) | Token assinado sem tabela; SMTP; envio assíncrono | BE-032, BE-085 | Fase 7 |
| [0013](0013-observacoes-tecnicas.md) | `technical_notes` separada; oficina não edita o veículo | BE-012 | Fase 7 |
| [0014](0014-sem-aguardando-peca.md) | Sem a etapa "aguardando peça" | — | Fase 7 |
| [0015](0015-moderacao-denuncias.md) | Efeito da denúncia, auditoria, autor abreviado | BE-061, BE-073 | Fase 5 |
| [0016](0016-fuso-do-negocio.md) | Fuso único `America/Sao_Paulo` | BE-022, BE-065 | Fase 7 |
| [0017](0017-mapa-sem-postgis.md) | Mapa por caixa envolvente + Haversine | BE-067 | Fase 7 |
| [0018](0018-desativacao-anonimizacao.md) | Desativação e anonimização de conta | BE-075, BE-078 | Fase 5 |
| [0019](0019-limites-e-busca.md) | Limites = `maxlength` da tela; busca sem acentos | BE-036, BE-086 | Fase 7 |
| [0020](0020-oficina-publica.md) | Oficina pública = ativa + cadastro concluído | BE-065…BE-068 | Fase 7 |
| [0021](0021-portas-e-mesma-origem.md) | Dev 8000/5500; produção na mesma origem | BE-034, BE-089 | Fase 7 |
| [0022](0022-hospedagem-tls-backup-tiles.md) | Compose + Nginx + TLS; backup diário (revisto por 0024–0026) | BE-088…BE-094 | Fase 7 |
| [0023](0023-nota-media-e-desempenho.md) | Nota média na consulta; metas de desempenho | BE-083 | Fase 6 |
| [0024](0024-mapa-osm-tiles-e-overpass.md) | Tiles do OSM público; estabelecimentos do OSM pela Overpass (cache, recuo, sem duplicatas) | BE-094 | BE-094 |
| [0025](0025-backup-rpo-rto.md) | RPO 24 h / RTO 8 h; agendador diário com recuperação; md5 por tabela; ensaio isolado | BE-090, BE-094 | BE-094 |
| [0026](0026-staging-local-e-navegadores.md) | Staging local `https://sam.localhost` (CA local, loopback); E2E Chromium + Firefox | BE-082, BE-094 | BE-094 |

Formato: Contexto, Decisão, Consequências, Tarefas. Decisão nova ou revista pelo
responsável: escreva um ADR novo que **substitui** o antigo (Status: "Substitui o ADR
NNNN") em vez de reescrever a história.
