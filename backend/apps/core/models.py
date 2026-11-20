from django.db import models


class JobHeartbeat(models.Model):
    """Última execução de cada rotina (BE-091/BE-092). Escrita por `apps.core.heartbeat`
    e pelo script de backup; lida pelo monitor e por `GET /api/health/jobs/`."""

    job_name = models.CharField(max_length=50, primary_key=True)
    date_last_run = models.DateTimeField()
    date_last_success = models.DateTimeField(null=True)
    date_last_failure = models.DateTimeField(null=True)
    last_error = models.TextField(null=True)
    details = models.JSONField(default=dict)

    class Meta:
        managed = False
        db_table = "job_heartbeat"

    def __str__(self):
        return self.job_name
