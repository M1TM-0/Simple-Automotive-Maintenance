
import apps.core.db
import apps.core.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_init_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegisterMaintenance',
            fields=[
                ('id_register_maintenance', models.BigAutoField(primary_key=True, serialize=False)),
                ('service_name', models.CharField(max_length=255)),
                ('date_maintenance', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('mileage_km', models.IntegerField(blank=True, null=True)),
                ('observations', models.TextField(blank=True, null=True)),
                ('interval_km', models.IntegerField(blank=True, null=True)),
                ('item_type', models.GeneratedField(db_persist=True, expression=models.Case(models.When(models.Q(('budget_item__isnull', False)), then=models.Value('service')), output_field=models.CharField(max_length=20)), output_field=models.CharField(max_length=20, null=True))),
                ('item_execution_status', models.GeneratedField(db_persist=True, expression=models.Case(models.When(models.Q(('budget_item__isnull', False)), then=models.Value('executed')), output_field=models.CharField(max_length=20)), output_field=models.CharField(max_length=20, null=True))),
            ],
            options={
                'db_table': 'register_maintenance',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='RegisterMaintenancePart',
            fields=[
                ('id_register_maintenance_part', models.BigAutoField(primary_key=True, serialize=False)),
                ('description', models.CharField(max_length=255)),
                ('brand', models.CharField(blank=True, max_length=255, null=True)),
                ('category', models.CharField(blank=True, max_length=255, null=True)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('date_maintenance', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('mileage_km', models.IntegerField(blank=True, null=True)),
                ('observations', models.TextField(blank=True, null=True)),
                ('item_type', models.GeneratedField(db_persist=True, expression=models.Value('product', output_field=models.CharField(max_length=20)), output_field=models.CharField(max_length=20))),
                ('item_execution_status', models.GeneratedField(db_persist=True, expression=models.Value('executed', output_field=models.CharField(max_length=20)), output_field=models.CharField(max_length=20))),
            ],
            options={
                'db_table': 'register_maintenance_part',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id_vehicle', models.BigAutoField(primary_key=True, serialize=False)),
                ('brand', models.CharField(max_length=255)),
                ('model', models.CharField(max_length=255)),
                ('year_fabrication', models.IntegerField()),
                ('year_model', models.IntegerField()),
                ('plate', models.CharField(max_length=7)),
                ('fuel', models.CharField(choices=[('gasolina', 'Gasolina'), ('etanol', 'Etanol'), ('diesel', 'Diesel'), ('flex', 'Flex'), ('eletrico', 'Elétrico'), ('hibrido', 'Híbrido'), ('gnv', 'GNV'), ('outro', 'Outro')], max_length=20)),
                ('exchange', models.CharField(choices=[('manual', 'Manual'), ('automatico', 'Automático'), ('automatizado', 'Automatizado'), ('dupla_embreagem', 'Dupla embreagem'), ('variavel', 'Variável (CVT)'), ('outro', 'Outro')], max_length=20)),
                ('version', models.CharField(blank=True, max_length=255, null=True)),
                ('motorization', models.CharField(blank=True, max_length=255, null=True)),
                ('color', models.CharField(blank=True, max_length=20, null=True)),
                ('information', models.TextField(blank=True, null=True)),
                ('photo_1', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('photo_2', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('photo_3', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('mileage_km', models.IntegerField(blank=True, null=True)),
                ('history_shared', models.BooleanField(db_default=False)),
            ],
            options={
                'db_table': 'vehicle',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VehicleMaintenanceHistory',
            fields=[
                ('pk', models.CompositePrimaryKey('record_type', 'id_record', blank=True, editable=False, primary_key=True, serialize=False)),
                ('record_type', models.CharField(max_length=10)),
                ('id_record', models.BigIntegerField()),
                ('id_vehicle', models.BigIntegerField()),
                ('id_attendance', models.BigIntegerField(null=True)),
                ('id_budget', models.BigIntegerField(null=True)),
                ('id_budget_item', models.BigIntegerField(null=True)),
                ('id_workshop', models.BigIntegerField(null=True)),
                ('id_service', models.BigIntegerField(null=True)),
                ('id_product', models.BigIntegerField(null=True)),
                ('id_service_item', models.BigIntegerField(null=True)),
                ('description', models.CharField(max_length=255)),
                ('brand', models.CharField(max_length=255, null=True)),
                ('category', models.CharField(max_length=255, null=True)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=10, null=True)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('date_maintenance', models.DateTimeField()),
                ('mileage_km', models.IntegerField(null=True)),
                ('observations', models.TextField(null=True)),
                ('interval_km', models.IntegerField(null=True)),
            ],
            options={
                'db_table': 'vw_vehicle_maintenance_history',
                'managed': False,
            },
        ),
    ]
