
import apps.core.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_init_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='OperationHour',
            fields=[
                ('id_operation_hour', models.BigAutoField(primary_key=True, serialize=False)),
                ('day_of_week', models.IntegerField()),
                ('opening_time', models.TimeField()),
                ('closing_time', models.TimeField()),
            ],
            options={
                'db_table': 'operation_hour',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PagWorkshop',
            fields=[
                ('id_pag_workshop', models.BigAutoField(primary_key=True, serialize=False)),
                ('description', models.TextField(blank=True, null=True)),
                ('photo_profile', apps.core.fields.StoredImageField(blank=True, db_default='default-profile.png', max_length=500, null=True)),
                ('photo_banner', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
            ],
            options={
                'db_table': 'pag_workshop',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PointOfInterest',
            fields=[
                ('id_point_of_interest', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('type', models.CharField(choices=[('oficina', 'Oficina'), ('borracharia', 'Borracharia'), ('posto_combustivel', 'Posto de combustível'), ('loja_autopecas', 'Loja de autopeças'), ('centro_automotivo', 'Centro automotivo'), ('concessionaria', 'Concessionária'), ('lava_jato', 'Lava-jato'), ('outro', 'Outro')], max_length=30)),
                ('latitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('longitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('address', models.TextField(blank=True, null=True)),
                ('external_source', models.CharField(blank=True, max_length=50, null=True)),
                ('external_id', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'db_table': 'point_of_interest',
                'managed': False,
            },
        ),
    ]
