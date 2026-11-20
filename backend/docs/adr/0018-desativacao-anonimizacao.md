# ADR 0018 — Desativação e anonimização de conta

- **Status:** Aceito por padrão — recomendação do backlog (DP-18), 2026-11
- **Tarefas:** BE-075, BE-078

## Contexto

Excluir cliente ou oficina é bloqueado pelas FKs `RESTRICT` que preservam atendimentos,
orçamentos, avaliações e denúncias. A LGPD (Lei 13.709/2018) dá ao titular o direito de
pedir a eliminação ou anonimização dos dados pessoais (art. 18, IV e VI), e permite
conservar o que for necessário para obrigação legal ou exercício de direitos (art. 16) —
aqui, o histórico de serviços prestados, que também é dado do outro lado (oficina ou
cliente) e base de avaliações.

## Decisão

1. **Nunca apagar a conta.** A administração (Django Admin, ADR 0003) **desativa**
   (`inactive`) ou **bloqueia** (`blocked`): login → 403, sessões abertas caem na
   requisição seguinte, a oficina some do mapa, do perfil e das vitrines.
2. **Anonimizar sob solicitação do titular** (ação do Django Admin, com confirmação,
   irreversível):
   - cliente: nome → "Anônimo"; e-mail → `anonimo-client-<id>@anonimizado.invalid`;
     telefone e foto removidos; favoritos e notificações dele apagados;
   - oficina: responsável → "Anônimo"; e-mail → `anonimo-workshop-<id>@anonimizado.invalid`;
     telefone e fotos da página removidos; notificações dela apagadas. **Nome fantasia
     e CNPJ ficam** (dados da empresa, identificam o prestador no histórico dos clientes
     e em registros fiscais);
   - ambos: senha trocada por hash inutilizável e status `inactive`; arquivos de foto
     apagados do storage depois do commit; a conta não pode ser reativada.
3. **Permanecem**: atendimentos, orçamentos, histórico de manutenção, veículos, mensagens
   de chat e avaliações (autor exibido como "Anônimo").
4. O e-mail original fica livre para um novo cadastro.

## Consequências

- Textos livres já gravados (mensagens de chat, comentários, notificações enviadas ao
  outro lado com o nome abreviado) não são reescritos; um pedido que exija isso é
  tratado caso a caso pelo admin.
- A anonimização usa o domínio reservado `.invalid` (RFC 2606): nenhum e-mail é entregue.
- Não há tela de autoatendimento (nenhuma tela do frontend pede); se vier, chamar
  `accounts.services.anonymize_account` exigindo a senha atual.
