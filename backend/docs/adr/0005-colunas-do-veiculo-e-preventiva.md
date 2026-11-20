# ADR 0005 — Colunas do veículo e manutenção preventiva

- **Status:** Aceito por padrão — recomendação do backlog (DP-05), 2026-11
- **Tarefas:** BE-008, BE-013, BE-077

## Contexto

O frontend tinha a quilometragem do veículo (P1), a chave "oficinas podem consultar o
histórico" (P2) e "próxima troca em km" com "Próximas manutenções" (P3) sem coluna no
`init.sql`. O backlog do produto (2.3 e MoSCoW 3.3, *Could have*) prevê o aviso
automático de manutenção preventiva. O histórico (`REGISTER_MAINTENANCE`) é só-inclusão.

## Decisão

1. `VEHICLE.mileage_km` e `VEHICLE.history_shared` (BE-008) e
   `REGISTER_MAINTENANCE.interval_km` opcional (BE-013), por migrations `RunSQL` de ida e volta.
2. **Cálculo no backend** (BE-077, `apps/vehicles/reminders.py`), o frontend só apresenta:
   - item = serviço do catálogo (`id_service`) ou, sem ele, o nome normalizado;
   - última execução = registro mais recente do item (manual ou de atendimento entregue);
     intervalo = o `interval_km` mais recente do item (a oficina não informa intervalo:
     a troca feita por ela reinicia o ciclo com o intervalo do cliente);
   - próxima = km da última execução + intervalo; situação `ok`, `soon` (falta até
     `SAM_MAINTENANCE_REMINDER_PERCENT` % do intervalo, padrão 10) ou `overdue`;
   - só quilometragem (não há intervalo em tempo no schema); peças não entram.
   Exposto em `GET /vehicles/{id}/upcoming-maintenance/`.
3. **Lembrete**: notificação ao cliente (sino, DP-11) **uma vez por ciclo**, registrada na
   tabela nova `MAINTENANCE_REMINDER` (`vehicles/0004`), com a última execução como chave
   única — o histórico não é alterado. Rotina `send_maintenance_reminders`, agendada no
   serviço `jobs` a cada hora (`--reminders-interval 3600`). Cliente bloqueado ou inativo
   não recebe aviso.

## Consequências

- O aviso depende de o cliente manter a km do veículo atualizada (edição do veículo ou
  registro manual com km maior, RI-11); a km do atendimento não muda a do veículo.
- Um ciclo avisado como `soon` não é avisado de novo ao vencer (critério "não repete").
- Aviso à oficina que fez o último serviço (opcional no backlog 2.3) não foi feito.
- Intervalo por tempo exigiria coluna nova (`interval_days`) e o mesmo cálculo por data.
