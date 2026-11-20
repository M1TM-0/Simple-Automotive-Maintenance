from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE NOTIFICATION ADD COLUMN url VARCHAR(255)",
                "ALTER TABLE NOTIFICATION ADD CONSTRAINT ck_notification_url "
                "CHECK (url IS NULL OR url ~ '^[a-z-]+\\.html(\\?[A-Za-z0-9_=&.-]*)?$')",
            ],
            reverse_sql=[
                "ALTER TABLE NOTIFICATION DROP CONSTRAINT ck_notification_url",
                "ALTER TABLE NOTIFICATION DROP COLUMN url",
            ],
        ),
    ]
