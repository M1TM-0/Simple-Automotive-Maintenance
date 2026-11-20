from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "CREATE INDEX idx_budget_workshop ON BUDGET (id_workshop)",
                "CREATE INDEX idx_message_unread ON MESSAGE (id_chat, id_client, id_workshop) "
                "WHERE status_message <> 'read'",
            ],
            reverse_sql=[
                "DROP INDEX idx_message_unread",
                "DROP INDEX idx_budget_workshop",
            ],
        ),
    ]
