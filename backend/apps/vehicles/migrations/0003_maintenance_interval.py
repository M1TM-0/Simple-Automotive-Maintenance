from django.db import migrations

VIEW_WITH_INTERVAL = """
CREATE OR REPLACE VIEW vw_vehicle_maintenance_history AS
SELECT rm.id_vehicle,
       'service'::TEXT              AS record_type,
       rm.id_register_maintenance   AS id_record,
       rm.id_attendance,
       rm.id_budget,
       rm.id_budget_item,
       a.id_workshop,
       rm.id_service,
       NULL::BIGINT                 AS id_product,
       NULL::BIGINT                 AS id_service_item,
       rm.service_name              AS description,
       NULL::VARCHAR                AS brand,
       NULL::VARCHAR                AS category,
       bi.quantity,
       bi.unit_price,
       rm.date_maintenance,
       rm.mileage_km,
       rm.observations,
       rm.interval_km
FROM REGISTER_MAINTENANCE rm
LEFT JOIN ATTENDANCE a   ON a.id_attendance = rm.id_attendance
LEFT JOIN BUDGET_ITEM bi ON bi.id_budget_item = rm.id_budget_item
UNION ALL
SELECT rmp.id_vehicle,
       'part'::TEXT,
       rmp.id_register_maintenance_part,
       rmp.id_attendance,
       rmp.id_budget,
       rmp.id_budget_item,
       rmp.id_workshop,
       NULL::BIGINT,
       rmp.id_product,
       rmp.id_service_item,
       rmp.description,
       rmp.brand,
       rmp.category,
       rmp.quantity,
       rmp.unit_price,
       rmp.date_maintenance,
       rmp.mileage_km,
       rmp.observations,
       NULL::INT
FROM REGISTER_MAINTENANCE_PART rmp
"""

VIEW_ORIGINAL = """
CREATE VIEW vw_vehicle_maintenance_history AS
SELECT rm.id_vehicle,
       'service'::TEXT              AS record_type,
       rm.id_register_maintenance   AS id_record,
       rm.id_attendance,
       rm.id_budget,
       rm.id_budget_item,
       a.id_workshop,
       rm.id_service,
       NULL::BIGINT                 AS id_product,
       NULL::BIGINT                 AS id_service_item,
       rm.service_name              AS description,
       NULL::VARCHAR                AS brand,
       NULL::VARCHAR                AS category,
       bi.quantity,
       bi.unit_price,
       rm.date_maintenance,
       rm.mileage_km,
       rm.observations
FROM REGISTER_MAINTENANCE rm
LEFT JOIN ATTENDANCE a   ON a.id_attendance = rm.id_attendance
LEFT JOIN BUDGET_ITEM bi ON bi.id_budget_item = rm.id_budget_item
UNION ALL
SELECT rmp.id_vehicle,
       'part'::TEXT,
       rmp.id_register_maintenance_part,
       rmp.id_attendance,
       rmp.id_budget,
       rmp.id_budget_item,
       rmp.id_workshop,
       NULL::BIGINT,
       rmp.id_product,
       rmp.id_service_item,
       rmp.description,
       rmp.brand,
       rmp.category,
       rmp.quantity,
       rmp.unit_price,
       rmp.date_maintenance,
       rmp.mileage_km,
       rmp.observations
FROM REGISTER_MAINTENANCE_PART rmp
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
        ("vehicles", "0002_vehicle_mileage_history_shared"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE REGISTER_MAINTENANCE ADD COLUMN interval_km INT "
                "CONSTRAINT ck_rm_interval CHECK (interval_km > 0)",
                VIEW_WITH_INTERVAL,
            ],
            reverse_sql=[
                "DROP VIEW vw_vehicle_maintenance_history",
                "ALTER TABLE REGISTER_MAINTENANCE DROP COLUMN interval_km",
                VIEW_ORIGINAL,
            ],
        ),
    ]
