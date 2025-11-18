from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_expand_room_xy_precision'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='categories',
            field=models.JSONField(blank=True, default=list),
        ),
    ]







