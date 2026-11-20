from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
        ("attendances", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE ATTENDANCE ADD COLUMN technical_notes TEXT",
            reverse_sql="ALTER TABLE ATTENDANCE DROP COLUMN technical_notes",
        ),
    ]
