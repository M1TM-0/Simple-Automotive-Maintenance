"""BE-077: lembretes de manutenção preventiva já enviados (um por ciclo).

`id_register_maintenance` UNIQUE é a garantia de "não repetir o aviso", inclusive
com duas execuções da rotina ao mesmo tempo (INSERT … ON CONFLICT DO NOTHING).
O histórico (`REGISTER_MAINTENANCE`) continua só-inclusão: o lembrete é dado
derivado, em tabela própria.
"""

import apps.core.db
import django.db.models.deletion
from django.db import migrations, models

CREATE_TABLE = """
CREATE TABLE MAINTENANCE_REMINDER (
    id_maintenance_reminder BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_register_maintenance BIGINT NOT NULL UNIQUE
        REFERENCES REGISTER_MAINTENANCE (id_register_maintenance) ON DELETE CASCADE,
    due_mileage_km INT NOT NULL CONSTRAINT ck_reminder_due CHECK (due_mileage_km > 0),
    status_reminder VARCHAR(20) NOT NULL
        CONSTRAINT ck_reminder_status CHECK (status_reminder IN ('soon', 'overdue')),
    date_sent TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class Migration(migrations.Migration):
    dependencies = [
        ("vehicles", "0003_maintenance_interval"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_TABLE, reverse_sql="DROP TABLE MAINTENANCE_REMINDER"
        ),
        migrations.CreateModel(
            name="MaintenanceReminder",
            fields=[
                (
                    "id_maintenance_reminder",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("due_mileage_km", models.IntegerField()),
                (
                    "status_reminder",
                    models.CharField(
                        choices=[("soon", "Próxima"), ("overdue", "Vencida")],
                        max_length=20,
                    ),
                ),
                (
                    "date_sent",
                    models.DateTimeField(db_default=apps.core.db.CurrentTimestamp()),
                ),
                (
                    "register_maintenance",
                    models.OneToOneField(
                        db_column="id_register_maintenance",
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="reminder",
                        to="vehicles.registermaintenance",
                    ),
                ),
            ],
            options={
                "db_table": "maintenance_reminder",
                "managed": False,
            },
        ),
    ]
