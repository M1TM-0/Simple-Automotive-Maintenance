from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
        ("vehicles", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE VEHICLE ADD COLUMN mileage_km INT "
                "CONSTRAINT ck_vehicle_mileage CHECK (mileage_km >= 0)",
                "ALTER TABLE VEHICLE ADD COLUMN history_shared BOOLEAN NOT NULL DEFAULT FALSE",
            ],
            reverse_sql=[
                "ALTER TABLE VEHICLE DROP COLUMN history_shared",
                "ALTER TABLE VEHICLE DROP COLUMN mileage_km",
            ],
        ),
    ]
