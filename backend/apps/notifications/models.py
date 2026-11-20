from apps.core.db import CurrentTimestamp
from django.db import models


class Notification(models.Model):
    id_notification = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(
        "accounts.Client",
        db_column="id_client",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="notifications",
    )
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())
    read_status = models.BooleanField(db_default=False)
    url = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "notification"
        managed = False
