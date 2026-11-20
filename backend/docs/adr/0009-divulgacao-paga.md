# ADR 0009 — Divulgação paga: preço, pagamento e ativação

- **Status:** Aceito por padrão — recomendação do backlog (DP-09), 2026-11
- **Tarefas:** BE-064, BE-076

## Contexto

`PROMOTION_ADVERTISEMENT.advertising_price` é obrigatório, mas nenhum requisito define o
preço; "pagamento integrado" é *Won't have*. O banco só deixa a divulgação `active` com
`payment_status = 'paid'` e dentro do período, e nenhuma rotina do schema a ativa quando
o período começa (só `complete_finished_advertisements`). A trigger que encerra as
divulgações de uma promoção desativada não mexe no pagamento.

## Decisão

1. **Preço** (BE-064): diárias arredondadas para cima × `SAM_ADVERTISING_PRICE_PER_DAY`
   (padrão 10,00), calculado pelo servidor. A divulgação nasce `pending/pending`.
2. **Pagamento manual**: sem gateway. O admin confere o recebimento por fora e usa o
   Django Admin (divulgações): *confirmar pagamento* (`pending|failed → paid`),
   *pagamento não identificado* (`pending → failed`) e *cancelar divulgação*.
3. **Ativação**: confirmada dentro do período → entra no ar na hora; antes do período →
   a rotina `run_expiration_jobs` (serviço `jobs`, a cada 60 s) a ativa quando
   `date_start` chega, desde que paga e com a promoção ativa. Não paga nunca é ativada.
4. **Estorno**: divulgação paga que termina `cancelled` (oficina desativou a promoção,
   promoção expirou antes de ir ao ar, moderação, admin) tem o pagamento marcado
   `refunded` = *marcado para estorno*; o admin devolve o valor por fora. O estorno é
   integral (sem proporcionalidade pelo tempo já veiculado). A rotina varre e marca os
   casos que nenhum serviço tratou (ex.: expiração).
5. A oficina é notificada da confirmação, da entrada no ar e do estorno.

## Consequências

- `refunded` não distingue "a devolver" de "devolvido"; se for preciso, criar um status
  novo por migration `RunSQL` (CHECK `ck_advertisement_payment`).
- Integração com gateway, se vier, substitui só a confirmação manual
  (`confirm_advertisement_payment`); ativação e estorno continuam iguais.
- A promoção é travada com `FOR NO KEY UPDATE` nos serviços para não causar deadlock
  com a ativação (a trigger da divulgação pega `FOR KEY SHARE` na promoção).
