from django.db import migrations, models


def populate_cached_fields(apps, schema_editor):
    Room = apps.get_model('accounts', 'Room')
    RoomParticipant = apps.get_model('accounts', 'RoomParticipant')
    for room in Room.objects.all():
        try:
            room.host_trust_score = float(getattr(room.created_by, 'trust_score', 0) or 0)
        except Exception:
            room.host_trust_score = 0.0
        try:
            room.current_participants_cached = RoomParticipant.objects.filter(room_id=room.id).count()
        except Exception:
            room.current_participants_cached = 0
        room.save(update_fields=['host_trust_score', 'current_participants_cached'])


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0009_convert_categories_to_codes'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='host_trust_score',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='room',
            name='current_participants_cached',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(populate_cached_fields, migrations.RunPython.noop),
    ]


