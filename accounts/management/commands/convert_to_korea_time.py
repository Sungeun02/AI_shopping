from django.core.management.base import BaseCommand
from accounts.models import Room, User, ChatMessage, Notification, AiRecommendLog, RoomRating
from django.utils import timezone
from django.utils import timezone as tz_util


class Command(BaseCommand):
    help = "기존 데이터베이스의 모든 시간을 한국 시간으로 변환합니다"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='실제로 수정하지 않고 미리보기만 합니다',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='모든 시간을 한국 시간으로 변환합니다',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("=== DRY RUN 모드 (실제 수정 안 함) ===\n"))
        
        seoul_tz = tz_util.get_fixed_timezone(540)  # UTC+9 (Asia/Seoul)
        total_fixed = 0
        
        # Room 모델의 meetup_at, created_at
        # 기존 데이터는 UTC로 저장되어 있으므로 한국 시간으로 변환
        self.stdout.write("Room 모델 변환 중...")
        rooms = Room.objects.all()
        for room in rooms:
            fixed = False
            # meetup_at: UTC로 저장된 것으로 가정하고 한국 시간으로 변환
            if room.meetup_at:
                if timezone.is_aware(room.meetup_at):
                    # aware datetime이면 한국 시간으로 변환
                    korea_time = timezone.localtime(room.meetup_at)
                    room.meetup_at = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    # naive datetime이지만 UTC로 저장된 것으로 가정
                    # UTC를 한국 시간으로 변환 (9시간 추가)
                    from datetime import timedelta
                    korea_time = room.meetup_at + timedelta(hours=9)
                    room.meetup_at = korea_time
                    fixed = True
            # created_at
            if room.created_at:
                if timezone.is_aware(room.created_at):
                    korea_time = timezone.localtime(room.created_at)
                    room.created_at = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    from datetime import timedelta
                    korea_time = room.created_at + timedelta(hours=9)
                    room.created_at = korea_time
                    fixed = True
            # settlement_created_at
            if room.settlement_created_at:
                if timezone.is_aware(room.settlement_created_at):
                    korea_time = timezone.localtime(room.settlement_created_at)
                    room.settlement_created_at = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    from datetime import timedelta
                    korea_time = room.settlement_created_at + timedelta(hours=9)
                    room.settlement_created_at = korea_time
                    fixed = True
            
            if fixed and options['fix']:
                room.save()
                total_fixed += 1
                self.stdout.write(f"  Room {room.id} 변환 완료")
        
        # User 모델의 created_at, updated_at
        self.stdout.write("User 모델 변환 중...")
        from datetime import timedelta
        users = User.objects.all()
        for user in users:
            fixed = False
            if user.created_at:
                if timezone.is_aware(user.created_at):
                    korea_time = timezone.localtime(user.created_at)
                    user.created_at = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    korea_time = user.created_at + timedelta(hours=9)
                    user.created_at = korea_time
                    fixed = True
            if user.updated_at:
                if timezone.is_aware(user.updated_at):
                    korea_time = timezone.localtime(user.updated_at)
                    user.updated_at = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    korea_time = user.updated_at + timedelta(hours=9)
                    user.updated_at = korea_time
                    fixed = True
            
            if fixed and options['fix']:
                user.save()
                total_fixed += 1
        
        # ChatMessage 모델의 created_at
        self.stdout.write("ChatMessage 모델 변환 중...")
        from datetime import timedelta
        messages = ChatMessage.objects.all()
        for msg in messages:
            fixed = False
            if timezone.is_aware(msg.created_at):
                korea_time = timezone.localtime(msg.created_at)
                msg.created_at = korea_time.replace(tzinfo=None)
                fixed = True
            else:
                korea_time = msg.created_at + timedelta(hours=9)
                msg.created_at = korea_time
                fixed = True
            if fixed and options['fix']:
                msg.save()
                total_fixed += 1
        
        # Notification 모델의 created_at
        self.stdout.write("Notification 모델 변환 중...")
        from datetime import timedelta
        notifications = Notification.objects.all()
        for notif in notifications:
            fixed = False
            if timezone.is_aware(notif.created_at):
                korea_time = timezone.localtime(notif.created_at)
                notif.created_at = korea_time.replace(tzinfo=None)
                fixed = True
            else:
                korea_time = notif.created_at + timedelta(hours=9)
                notif.created_at = korea_time
                fixed = True
            if fixed and options['fix']:
                notif.save()
                total_fixed += 1
        
        # AiRecommendLog 모델의 desired_time, created_at
        self.stdout.write("AiRecommendLog 모델 변환 중...")
        from datetime import timedelta
        logs = AiRecommendLog.objects.all()
        for log in logs:
            fixed = False
            if log.desired_time:
                if timezone.is_aware(log.desired_time):
                    korea_time = timezone.localtime(log.desired_time)
                    log.desired_time = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    korea_time = log.desired_time + timedelta(hours=9)
                    log.desired_time = korea_time
                    fixed = True
            if log.created_at:
                if timezone.is_aware(log.created_at):
                    korea_time = timezone.localtime(log.created_at)
                    log.created_at = korea_time.replace(tzinfo=None)
                    fixed = True
                else:
                    korea_time = log.created_at + timedelta(hours=9)
                    log.created_at = korea_time
                    fixed = True
            
            if fixed and options['fix']:
                log.save()
                total_fixed += 1
        
        # RoomRating 모델의 created_at
        self.stdout.write("RoomRating 모델 변환 중...")
        from datetime import timedelta
        ratings = RoomRating.objects.all()
        for rating in ratings:
            fixed = False
            if timezone.is_aware(rating.created_at):
                korea_time = timezone.localtime(rating.created_at)
                rating.created_at = korea_time.replace(tzinfo=None)
                fixed = True
            else:
                korea_time = rating.created_at + timedelta(hours=9)
                rating.created_at = korea_time
                fixed = True
            if fixed and options['fix']:
                rating.save()
                total_fixed += 1
        
        # RoomParticipant 모델의 joined_at
        from accounts.models import RoomParticipant
        self.stdout.write("RoomParticipant 모델 변환 중...")
        from datetime import timedelta
        participants = RoomParticipant.objects.all()
        for participant in participants:
            fixed = False
            if timezone.is_aware(participant.joined_at):
                korea_time = timezone.localtime(participant.joined_at)
                participant.joined_at = korea_time.replace(tzinfo=None)
                fixed = True
            else:
                korea_time = participant.joined_at + timedelta(hours=9)
                participant.joined_at = korea_time
                fixed = True
            if fixed and options['fix']:
                participant.save()
                total_fixed += 1
        
        if options['fix']:
            self.stdout.write(
                self.style.SUCCESS(f"\n총 {total_fixed}개의 레코드를 한국 시간으로 변환했습니다.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "\n시간 확인 완료. 실제로 변환하려면 --fix 옵션을 사용하세요."
                )
            )

