# ADR 0012 — Redefinição de senha

- **Status:** Aceito por padrão — recomendação do backlog (DP-12), 2026-11
- **Tarefas:** BE-032, BE-085

## Contexto

Sem recuperação por e-mail o usuário que esquece a senha perde a conta.

## Decisão

- Token assinado com validade de 1 h, preso ao *fingerprint* do hash atual (sem tabela):
  usar o token ou trocar a senha o invalida.
- SMTP configurável (`EMAIL_*`); console em desenvolvimento.
- Resposta idêntica para e-mail existente e inexistente; em produção o envio é assíncrono
  (`SAM_EMAIL_ASYNC=True`) para o tempo de resposta também não denunciar.

## Consequências

- Se o worker reiniciar no meio do envio, o e-mail se perde e o usuário pede de novo.
