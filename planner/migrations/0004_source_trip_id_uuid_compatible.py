from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0003_add_source_trip_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='triprecord',
            name='source_trip_id',
            field=models.CharField(
                blank=True,
                editable=False,
                help_text='Identifiant du Trip du tracker synchronisé',
                max_length=36,
                null=True,
                unique=True,
            ),
        ),
    ]
