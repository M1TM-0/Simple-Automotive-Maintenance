
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
            name='AdvertisementEffective',
            fields=[
                ('id_promotion_advertisement', models.BigIntegerField(primary_key=True, serialize=False)),
                ('image_url', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('date_creation', models.DateTimeField()),
                ('date_start', models.DateTimeField()),
                ('date_end', models.DateTimeField()),
                ('advertising_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_status', models.CharField(max_length=30)),
                ('status_advertisement', models.CharField(max_length=30)),
                ('is_running_now', models.BooleanField()),
            ],
            options={
                'db_table': 'vw_advertisement_effective',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Promotion',
            fields=[
                ('id_promotion', models.BigAutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('type_discount', models.CharField(choices=[('percentage', 'Percentual'), ('fixed', 'Valor fixo')], max_length=50)),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=10)),
                ('date_start', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('date_end', models.DateTimeField()),
                ('image_url', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('status_promotion', models.CharField(choices=[('active', 'Ativa'), ('inactive', 'Inativa'), ('expired', 'Expirada')], db_default='active', max_length=50)),
            ],
            options={
                'db_table': 'promotion',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PromotionAdvertisement',
            fields=[
                ('id_promotion_advertisement', models.BigAutoField(primary_key=True, serialize=False)),
                ('image_url', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('date_creation', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('date_start', models.DateTimeField()),
                ('date_end', models.DateTimeField()),
                ('advertising_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_status', models.CharField(choices=[('pending', 'Pendente'), ('paid', 'Pago'), ('failed', 'Falhou'), ('refunded', 'Estornado')], db_default='pending', max_length=30)),
                ('status_advertisement', models.CharField(choices=[('pending', 'Pendente'), ('active', 'Ativa'), ('completed', 'Concluída'), ('cancelled', 'Cancelada')], db_default='pending', max_length=30)),
            ],
            options={
                'db_table': 'promotion_advertisement',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PromotionEffective',
            fields=[
                ('id_promotion', models.BigIntegerField(primary_key=True, serialize=False)),
                ('id_workshop_service', models.BigIntegerField(null=True)),
                ('id_product', models.BigIntegerField(null=True)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(null=True)),
                ('type_discount', models.CharField(max_length=50)),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=10)),
                ('date_start', models.DateTimeField()),
                ('date_end', models.DateTimeField()),
                ('image_url', apps.core.fields.StoredImageField(blank=True, max_length=500, null=True)),
                ('status_promotion', models.CharField(max_length=50)),
                ('effective_status', models.CharField(max_length=20)),
                ('is_valid_now', models.BooleanField()),
            ],
            options={
                'db_table': 'vw_promotion_effective',
                'managed': False,
            },
        ),
    ]
