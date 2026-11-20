"""BE-091/BE-092: batimento das rotinas (expiração, lembretes, backup).

Uma linha por rotina, atualizada a cada execução. O monitor (`manage.py monitor`) e
`GET /api/health/jobs/` alertam quando a última execução bem-sucedida fica velha
("sem execução do job nos últimos 15 minutos", seção 13.5 do backlog). O backup
(deploy/backup/backup.sh) grava pela mesma tabela via psql.

Tabela de operação, fora do domínio do `init.sql`: não tem chave estrangeira e pode
ser apagada sem efeito nos dados do negócio.
"""

from django.db import migrations, models

CREATE_TABLE = """
CREATE TABLE JOB_HEARTBEAT (
    job_name VARCHAR(50) PRIMARY KEY
        CONSTRAINT ck_job_heartbeat_name CHECK (job_name ~ '^[a-z][a-z0-9_]*$'),
    date_last_run TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    date_last_success TIMESTAMPTZ,
    date_last_failure TIMESTAMPTZ,
    last_error TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_perf_indexes"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TABLE, reverse_sql="DROP TABLE JOB_HEARTBEAT"),
        migrations.CreateModel(
            name="JobHeartbeat",
            fields=[
                (
                    "job_name",
                    models.CharField(max_length=50, primary_key=True, serialize=False),
                ),
                ("date_last_run", models.DateTimeField()),
                ("date_last_success", models.DateTimeField(null=True)),
                ("date_last_failure", models.DateTimeField(null=True)),
                ("last_error", models.TextField(null=True)),
                ("details", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "job_heartbeat",
                "managed": False,
            },
        ),
    ]
