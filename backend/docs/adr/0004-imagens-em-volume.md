# ADR 0004 — Imagens em sistema de arquivos atrás de storage abstrato

- **Status:** Aceito por padrão — recomendação do backlog (DP-04), 2026-11
- **Tarefas:** BE-001, BE-021, BE-089, BE-090

## Contexto

Fotos de perfil, da oficina, de veículos (3 posições), de produtos e de promoções são
enviadas pelo frontend em multipart. O banco guarda só o caminho.

## Decisão

- Arquivos no `default_storage` (sistema de arquivos, volume `media`), com nome UUID.
- Conteúdo validado pelo formato real e regravado sem metadados (JPEG/PNG/WEBP; 5 MB,
  4096 px). Arquivo substituído só é apagado depois do commit (`apply_image_changes`).
- Produção: o Nginx serve `/media/` **só** com extensão de imagem, com `nosniff`, CSP
  `sandbox` e cache longo (nome nunca muda de conteúdo).

## Consequências

- Backup próprio da mídia, junto do dump e com hash de cada arquivo (BE-090).
- Migrar para S3 (ou similar) = trocar o backend de storage; o contrato da API (URLs)
  não muda.
