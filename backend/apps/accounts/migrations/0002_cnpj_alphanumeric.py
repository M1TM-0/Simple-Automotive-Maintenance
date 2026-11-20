from django.db import migrations

# Desde 31/07/2026 a Receita Federal emite CNPJs alfanuméricos: 12 caracteres
# [0-9A-Z] + 2 dígitos verificadores numéricos. Os CNPJs numéricos continuam válidos.
ALLOW_ALPHANUMERIC = (
    "ALTER TABLE WORKSHOP DROP CONSTRAINT ck_workshop_cnpj, "
    "ADD CONSTRAINT ck_workshop_cnpj CHECK (cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$')"
)

# Só funciona se não houver CNPJ alfanumérico cadastrado.
NUMERIC_ONLY = (
    "ALTER TABLE WORKSHOP DROP CONSTRAINT ck_workshop_cnpj, "
    "ADD CONSTRAINT ck_workshop_cnpj CHECK (cnpj ~ '^[0-9]{14}$')"
)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=ALLOW_ALPHANUMERIC, reverse_sql=NUMERIC_ONLY),
    ]
