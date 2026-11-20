
import apps.core.db
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_init_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='Chat',
            fields=[
                ('id_chat', models.BigAutoField(primary_key=True, serialize=False)),
                ('date_creation', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('status_chat', models.CharField(choices=[('active', 'Ativa'), ('archived', 'Arquivada'), ('closed', 'Encerrada')], db_default='active', max_length=50)),
            ],
            options={
                'db_table': 'chat',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id_message', models.BigAutoField(primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('date_sent', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('status_message', models.CharField(choices=[('sent', 'Enviada'), ('delivered', 'Entregue'), ('read', 'Lida')], db_default='sent', max_length=50)),
            ],
            options={
                'db_table': 'message',
                'managed': False,
            },
        ),
    ]
