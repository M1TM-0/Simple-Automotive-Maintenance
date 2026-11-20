from django.db import migrations

MERGE_DUPLICATES = """
WITH ranked AS (
    SELECT id_chat,
           FIRST_VALUE(id_chat) OVER (
               PARTITION BY id_client, id_workshop ORDER BY date_creation, id_chat
           ) AS keep_id
    FROM CHAT
),
duplicates AS (
    SELECT id_chat, keep_id FROM ranked WHERE id_chat <> keep_id
),
moved AS (
    UPDATE MESSAGE m
    SET id_chat = d.keep_id
    FROM duplicates d
    WHERE m.id_chat = d.id_chat
    RETURNING m.id_message
)
DELETE FROM CHAT c USING duplicates d WHERE c.id_chat = d.id_chat
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
        ("chat", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                MERGE_DUPLICATES,
                "ALTER TABLE CHAT ADD CONSTRAINT uq_chat_client_workshop UNIQUE (id_client, id_workshop)",
            ],
            reverse_sql="ALTER TABLE CHAT DROP CONSTRAINT uq_chat_client_workshop",
        ),
    ]
