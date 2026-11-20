
import apps.core.db
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_init_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='Denunciation',
            fields=[
                ('id_denunciation', models.BigAutoField(primary_key=True, serialize=False)),
                ('reason', models.CharField(choices=[('inappropriate_content', 'Conteúdo inapropriado'), ('offensive_language', 'Linguagem ofensiva'), ('harassment', 'Assédio'), ('spam', 'Spam'), ('false_information', 'Informação falsa'), ('fraud', 'Fraude'), ('other', 'Outro')], max_length=50)),
                ('description', models.TextField(blank=True, null=True)),
                ('date_creation', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('status_denunciation', models.CharField(choices=[('pending', 'Pendente'), ('in_review', 'Em análise'), ('upheld', 'Procedente'), ('dismissed', 'Improcedente')], db_default='pending', max_length=30)),
                ('moderation_decision', models.TextField(blank=True, null=True)),
                ('date_resolution', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'denunciation',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id_review', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rating', models.IntegerField()),
                ('comment', models.TextField(blank=True, null=True)),
                ('date_creation', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('workshop_response', models.TextField(blank=True, null=True)),
                ('date_response', models.DateTimeField(blank=True, null=True)),
                ('status_review', models.CharField(choices=[('published', 'Publicada'), ('hidden', 'Oculta'), ('under_review', 'Em análise')], db_default='published', max_length=20)),
            ],
            options={
                'db_table': 'review',
                'managed': False,
            },
        ),
    ]
