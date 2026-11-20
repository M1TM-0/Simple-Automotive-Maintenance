# Diagramas históricos

`DIAGRAMA_SAM_conceitual_2026-10.svg` é o modelo conceitual original (draw.io, outubro
de 2026), mantido como registro do projeto. Ele **não** confere com o banco: usa UUID,
status numéricos `{1-4}` e não tem `PROMOTION_ADVERTISEMENT`, `REGISTER_MAINTENANCE_PART`,
`MAINTENANCE_REMINDER` nem `JOB_HEARTBEAT`.

O diagrama atual é `../DIAGRAMA_SAM.svg`, gerado do banco migrado por
`python manage.py schema_diagram` (BE-093); um teste reprova se ele ficar desatualizado.
