# Generated manually

from django.db import migrations


def recalculate_trust_scores(apps, schema_editor):
    """모든 사용자의 trust_score를 초기값 3.0과 받은 평점들의 평균으로 재계산"""
    User = apps.get_model('accounts', 'User')
    RoomRating = apps.get_model('accounts', 'RoomRating')
    Room = apps.get_model('accounts', 'Room')
    
    # 모든 사용자의 trust_score 재계산
    for user in User.objects.all():
        all_ratings = RoomRating.objects.filter(host=user)
        rating_count = all_ratings.count()
        
        if rating_count > 0:
            # 모든 평점의 합계 계산
            total_rating = sum(r.rating for r in all_ratings)
            # 초기값 3.0을 포함하여 평균 계산 (평점 개수 + 1)
            avg_rating = (3.0 + total_rating) / (rating_count + 1)
        else:
            # 평점이 없으면 기본값 3.0 유지
            avg_rating = 3.0
        
        user.trust_score = round(avg_rating, 1)
        user.save(update_fields=['trust_score'])
        
        # 해당 사용자가 방장인 모든 Room의 host_trust_score도 업데이트
        Room.objects.filter(created_by=user).update(host_trust_score=user.trust_score)


def reverse_recalculate_trust_scores(apps, schema_editor):
    """역방향 마이그레이션 (필요시)"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_update_trust_scores'),
    ]

    operations = [
        migrations.RunPython(recalculate_trust_scores, reverse_recalculate_trust_scores),
    ]





