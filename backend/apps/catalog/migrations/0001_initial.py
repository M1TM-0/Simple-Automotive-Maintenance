
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
            name='Product',
            fields=[
                ('id_product', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('category', models.CharField(blank=True, max_length=255, null=True)),
                ('brand', models.CharField(blank=True, max_length=255, null=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('disponibility', models.BooleanField(db_default=True)),
                ('photo', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('created_at', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('active', models.BooleanField(db_default=True)),
            ],
            options={
                'db_table': 'product',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id_service', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('active', models.BooleanField(db_default=True)),
            ],
            options={
                'db_table': 'service',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ServiceCategory',
            fields=[
                ('id_service_category', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'service_category',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='WorkshopService',
            fields=[
                ('id_workshop_service', models.BigAutoField(primary_key=True, serialize=False)),
                ('name_local', models.CharField(blank=True, max_length=255, null=True)),
                ('description_local', models.TextField(blank=True, null=True)),
                ('price_base', models.DecimalField(decimal_places=2, max_digits=10)),
                ('duration_estimate', models.IntegerField()),
                ('disponibility', models.BooleanField(db_default=True)),
                ('status_solicitation', models.CharField(blank=True, choices=[('pending', 'Pendente'), ('approved', 'Aprovada'), ('rejected', 'Rejeitada')], max_length=50, null=True)),
                ('motivation_rejection', models.TextField(blank=True, null=True)),
                ('date_solicitation_response', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
            ],
            options={
                'db_table': 'workshop_service',
                'managed': False,
            },
        ),
    ]
