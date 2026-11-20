
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
            name='Client',
            fields=[
                ('id_client', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('email', models.CharField(max_length=255)),
                ('password_hash', models.CharField(max_length=255)),
                ('phone_number', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('status', models.CharField(choices=[('active', 'Ativa'), ('inactive', 'Inativa'), ('blocked', 'Bloqueada')], db_default='active', max_length=50)),
                ('photo_profile', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
            ],
            options={
                'db_table': 'client',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id_favorite', models.BigAutoField(primary_key=True, serialize=False)),
                ('date_creation', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
            ],
            options={
                'db_table': 'favorite',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Workshop',
            fields=[
                ('id_workshop', models.BigAutoField(primary_key=True, serialize=False)),
                ('name_fantasy', models.CharField(max_length=255)),
                ('name_responsible', models.CharField(max_length=255)),
                ('email', models.CharField(max_length=255)),
                ('password_hash', models.CharField(max_length=255)),
                ('phone_number', models.CharField(blank=True, max_length=255, null=True)),
                ('cnpj', models.CharField(max_length=14, unique=True)),
                ('created_at', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('status', models.CharField(choices=[('active', 'Ativa'), ('inactive', 'Inativa'), ('blocked', 'Bloqueada')], db_default='active', max_length=50)),
            ],
            options={
                'db_table': 'workshop',
                'managed': False,
            },
        ),
    ]
