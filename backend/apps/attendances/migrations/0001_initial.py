
import apps.core.db
import datetime
import django.db.models.expressions
import django.db.models.functions.math
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_init_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attendance',
            fields=[
                ('id_attendance', models.BigAutoField(primary_key=True, serialize=False)),
                ('date_attendance', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('status_attendance', models.CharField(choices=[('requested', 'Solicitado'), ('budgeted', 'Orçado'), ('waiting_approval', 'Aguardando aprovação'), ('approved', 'Aprovado'), ('in_progress', 'Em andamento'), ('completed', 'Concluído'), ('delivered', 'Entregue'), ('canceled', 'Cancelado')], db_default='requested', max_length=20)),
                ('mileage_km', models.IntegerField(blank=True, null=True)),
                ('observations', models.TextField(blank=True, null=True)),
                ('technical_notes', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'attendance',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Budget',
            fields=[
                ('id_budget', models.BigAutoField(primary_key=True, serialize=False)),
                ('date_creation', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
                ('date_validity', models.DateTimeField(db_default=django.db.models.expressions.CombinedExpression(apps.core.db.CurrentTimestamp(), '+', models.Value(datetime.timedelta(days=7))))),
                ('total_price', models.DecimalField(db_default=Decimal('0'), decimal_places=2, max_digits=12)),
                ('status_budget', models.CharField(choices=[('pending', 'Pendente'), ('approved', 'Aprovado'), ('rejected', 'Recusado'), ('cancelled', 'Cancelado'), ('expired', 'Expirado')], db_default='pending', max_length=50)),
                ('date_response', models.DateTimeField(blank=True, null=True)),
                ('observations', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'budget',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='BudgetItem',
            fields=[
                ('id_budget_item', models.BigAutoField(primary_key=True, serialize=False)),
                ('item_type', models.CharField(choices=[('service', 'Serviço'), ('product', 'Produto'), ('labor', 'Mão de obra'), ('other', 'Outro')], max_length=20)),
                ('service_item_type', models.GeneratedField(db_persist=True, expression=models.Case(models.When(models.Q(('service_item__isnull', False)), then=models.Value('service')), output_field=models.CharField(max_length=20)), output_field=models.CharField(max_length=20, null=True))),
                ('description', models.CharField(max_length=255)),
                ('quantity', models.DecimalField(db_default=Decimal('1'), decimal_places=3, max_digits=10)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('subtotal', models.GeneratedField(db_persist=True, expression=django.db.models.functions.math.Round(django.db.models.expressions.CombinedExpression(models.F('quantity'), '*', models.F('unit_price')), precision=2), output_field=models.DecimalField(decimal_places=2, max_digits=12))),
                ('execution_status', models.CharField(choices=[('pending', 'Pendente'), ('executed', 'Executado'), ('not_executed', 'Não executado')], db_default='pending', max_length=20)),
                ('executed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(db_default=apps.core.db.CurrentTimestamp())),
            ],
            options={
                'db_table': 'budget_item',
                'managed': False,
            },
        ),
    ]
