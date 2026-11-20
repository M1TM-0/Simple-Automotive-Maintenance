# ADR 0015 — Moderação: efeito da denúncia e auditoria

- **Status:** Aceito por padrão — recomendação do backlog (DP-15), 2026-11
- **Tarefas:** BE-061, BE-066, BE-073

## Contexto

O banco guarda o ciclo da denúncia (`pending → in_review → upheld | dismissed`, finais
imutáveis) mas deixa ao backend o efeito sobre o conteúdo, e `DENUNCIATION` não registra
quem moderou.

## Decisão

1. **Denunciar não oculta nada** (BE-061). Só a moderação decide.
2. **Resolver exige `moderation_decision`** (400). Denúncia resolvida → 409; repetir o
   mesmo status → 409.
3. **Efeito de `upheld`**:
   - avaliação → `hidden` (sai do perfil público, da nota média e do mapa);
   - promoção → `inactive` (a trigger cancela as divulgações; as pagas vão para estorno,
     ADR 0009); promoção já expirada ou inativa fica como está;
   - divulgação → `cancelled` (estorno se paga); a concluída fica como está.
   `dismissed` não muda o conteúdo. Outras denúncias abertas sobre o mesmo conteúdo
   continuam na fila (cada denunciante recebe a própria resolução).
4. **Ocultar avaliação** também pode ser feito direto (`POST /admin/reviews/{id}/hide/`,
   idempotente).
5. **Auditoria por log estruturado**, sem coluna nova: `sam.audit` registra admin, ação,
   alvo, status HTTP e a transição (`from_status`, `to_status`). Retenção dos logs é
   tema da implantação (BE-092).
6. **Notificações**: o denunciante recebe o resultado (sem o texto interno da decisão);
   a oficina é avisada quando a promoção/divulgação dela sai do ar.
7. **Autor exibido** em avaliações públicas: primeiro nome + inicial do sobrenome.

## Consequências

- Para consultar "quem decidiu" é preciso o log; se virar requisito de tela, criar a
  coluna `moderated_by` por migration e preencher pelo serviço.
