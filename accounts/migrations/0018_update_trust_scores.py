# Generated manually

from django.db import migrations


def update_trust_scores(apps, schema_editor):
    """기존 사용자들의 trust_score를 3.0으로 업데이트하고, 모든 Room의 host_trust_score를 동기화"""
    User = apps.get_model('accounts', 'User')
    Room = apps.get_model('accounts', 'Room')
    
    # 기존 사용자들의 trust_score가 0.0이거나 None인 경우 3.0으로 설정
    User.objects.filter(trust_score=0.0).update(trust_score=3.0)
    User.objects.filter(trust_score__isnull=True).update(trust_score=3.0)
    
    # 모든 Room의 host_trust_score를 방장의 최신 trust_score로 업데이트
    for room in Room.objects.select_related('created_by').all():
        try:
            host_trust_score = float(getattr(room.created_by, 'trust_score', 3.0) or 3.0)
            if host_trust_score == 0:
                host_trust_score = 3.0
            room.host_trust_score = host_trust_score
            room.save(update_fields=['host_trust_score'])
        except Exception:
            room.host_trust_score = 3.0
            room.save(update_fields=['host_trust_score'])


def reverse_update_trust_scores(apps, schema_editor):
    """역방향 마이그레이션 (필요시)"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_alter_user_trust_score_roomrating'),
    ]

    operations = [
        migrations.RunPython(update_trust_scores, reverse_update_trust_scores),
    ]

