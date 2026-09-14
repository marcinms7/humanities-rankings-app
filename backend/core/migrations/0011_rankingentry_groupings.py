from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0010_shared_genre_taxonomy')]

    operations = [
        migrations.AddField(
            model_name='rankingentry',
            name='groupings',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
