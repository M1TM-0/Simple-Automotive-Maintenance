# ADR 0020 — Visibilidade pública da oficina

- **Status:** Aceito por padrão — recomendação do backlog (DP-20), 2026-11
- **Tarefas:** BE-065 a BE-068

## Contexto

Perfil, mapa e vitrine precisam da mesma regra de "quem aparece".

## Decisão

- Pública = `active` **e** cadastro concluído (≥ 1 serviço não rejeitado):
  `apps/workshops/selectors.py → public_workshops()`.
- Leituras públicas nunca devolvem CNPJ, e-mail ou responsável.
- Galeria de fotos fora do escopo.

## Consequências

- Bloquear a oficina no Django Admin a tira do mapa e do perfil na hora.
