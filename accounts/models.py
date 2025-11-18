from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone


class User(AbstractUser):
    """사용자 모델"""
    # 부모(AbstractUser)의 email 필드를 사용하지 않음
    email = None
    first_name = None
    last_name = None

    name = models.CharField(max_length=10)
    age = models.IntegerField(null=True, blank=True)
    GENDER_CHOICES = (
        ("M", "남성"),
        ("F", "여성"),
        ("U", "기타/미상"),
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    trust_score = models.FloatField(default=3.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username


class Room(models.Model):
    """장보기 팀 방"""
    STATUS_RECRUITING = 'RECRUITING'
    STATUS_FULL = 'FULL'
    STATUS_DONE = 'DONE'
    STATUS_CHOICES = (
        (STATUS_RECRUITING, '모집중'),
        (STATUS_FULL, '인원 마감'),
        (STATUS_DONE, '완료'),
    )

    mart_name = models.CharField(max_length=100)
    meetup_at = models.DateTimeField()
    max_participants = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECRUITING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_rooms')
    created_at = models.DateTimeField(auto_now_add=True)

    # 위치/주소 정보 (서울시 API 등에서 수집한 값 저장)
    road_address = models.CharField(max_length=255, blank=True, default="")  # 도로명 주소
    # 일부 공공데이터 API는 TM 좌표 등 큰 값이므로 자릿수 여유를 둔다
    x = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)  # 경도/혹은 X
    y = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)  # 위도/혹은 Y

    # 카테고리 (다중 선택)
    # 저장 형식: JSON 배열의 정수 코드 (예: [1, 5, 10])
    CATEGORY_MAP = {
        1: "채소/과일",
        2: "육류/유제품",
        3: "해산물",
        4: "쌀/곡류",
        5: "냉장/냉동/인스턴트",
        6: "음료/주류",
        7: "건강식품",
        8: "반려동물 용품",
        9: "문구/패션/생활",
        10: "기타",
    }
    # 기존 문자열 리스트는 호환을 위해 유지 (검증 등에 사용 가능)
    CATEGORY_LIST = list(CATEGORY_MAP.values())
    categories = models.JSONField(default=list, blank=True)

    # 캐시/요약 정보
    host_trust_score = models.FloatField(default=0)
    current_participants_cached = models.PositiveIntegerField(default=0)
    
    # 정산 결과
    settlement_result = models.JSONField(default=list, blank=True, null=True)  # OCR 결과 텍스트 리스트
    settlement_created_at = models.DateTimeField(null=True, blank=True)  # 정산 완료 시간

    class Meta:
        ordering = ['meetup_at', 'id']

    def __str__(self) -> str:
        return f"{self.mart_name} / {self.meetup_at:%Y-%m-%d %H:%M}"

    @property
    def current_participants(self) -> int:
        try:
            return int(self.current_participants_cached)
        except Exception:
            return self.participants.count()

    def is_joinable(self) -> bool:
        """방 참여 가능 여부 확인
        - 모집중 상태여야 함
        - 인원이 남아있어야 함
        - 약속 시간이 아직 지나지 않았어야 함
        - 약속 시간 10분 전까지는 참여 가능
        """
        if self.status != self.STATUS_RECRUITING:
            return False
        if self.current_participants >= self.max_participants:
            return False
        now = timezone.now()
        # 약속 시간이 이미 지났거나, 10분 이내면 참여 불가
        from datetime import timedelta
        cutoff_time = self.meetup_at - timedelta(minutes=10)
        if now >= cutoff_time:
            return False
        return True

    def update_current_participants(self) -> None:
        """현재 참여자 수를 실제 데이터베이스에서 계산하여 캐시에 저장"""
        count = self.participants.count()
        self.current_participants_cached = count
        self.save(update_fields=['current_participants_cached'])

    def update_status(self) -> None:
        """방 상태 자동 업데이트
        - 인원이 가득 차면 STATUS_FULL
        - 약속 시간 10분 전이면 STATUS_FULL (모집완료)
        - 약속 시간이 지나면 STATUS_DONE
        """
        from datetime import timedelta
        now = timezone.now()
        
        if self.current_participants >= self.max_participants:
            self.status = self.STATUS_FULL
        # 약속 시간 10분 전이면 모집완료로 변경
        elif self.status == self.STATUS_RECRUITING:
            cutoff_time = self.meetup_at - timedelta(minutes=10)
            if now >= cutoff_time:
                self.status = self.STATUS_FULL
        if self.meetup_at < now:
            self.status = self.STATUS_DONE
        self.save(update_fields=['status'])


class RoomParticipant(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='joined_rooms')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('room', 'user')
        indexes = [
            models.Index(fields=['room', 'user']),
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.room}"


# RoomParticipant가 생성되거나 삭제될 때 Room의 현재 인원을 자동으로 업데이트
@receiver(post_save, sender=RoomParticipant)
def update_room_participants_on_save(sender, instance, created, **kwargs):
    """참여자가 추가될 때 방의 현재 인원 업데이트"""
    if created:
        instance.room.update_current_participants()
        instance.room.update_status()


@receiver(post_delete, sender=RoomParticipant)
def update_room_participants_on_delete(sender, instance, **kwargs):
    """참여자가 삭제될 때 방의 현재 인원 업데이트"""
    instance.room.update_current_participants()
    instance.room.update_status()


class ChatMessage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    content = models.TextField()
    is_system = models.BooleanField(default=False)  # 시스템 메시지 여부
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class Notification(models.Model):
    """알림 모델"""
    TYPE_CHAT = 'CHAT'
    TYPE_JOIN = 'JOIN'
    TYPE_LEAVE = 'LEAVE'
    TYPE_DONE = 'DONE'
    TYPE_DELETE = 'DELETE'
    TYPE_CHOICES = (
        (TYPE_CHAT, '채팅 메시지'),
        (TYPE_JOIN, '참여'),
        (TYPE_LEAVE, '나가기'),
        (TYPE_DONE, '모집 완료'),
        (TYPE_DELETE, '방 삭제'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, related_name='notifications', null=True, blank=True)
    notification_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    message = models.CharField(max_length=255)
    deleted_room_name = models.CharField(max_length=255, null=True, blank=True)  # 삭제된 방의 마트 이름 저장
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]
    
    def __str__(self) -> str:
        room_name = self.room.mart_name if self.room else (self.deleted_room_name or "(삭제된 방)")
        return f"{self.user.username} - {self.get_notification_type_display()} - {room_name}"


class AiRecommendLog(models.Model):
    """AI 추천 요청 로그
    - 사용자가 선택한 파라미터와 상위 결과 요약을 저장한다
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    lat = models.FloatField()
    lng = models.FloatField()
    desired_time = models.DateTimeField()
    categories = models.JSONField(default=list, blank=True)  # 정수 코드 배열
    top_results = models.JSONField(default=list, blank=True)  # 예: [{"id": 12, "score": 0.87}, ...]
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"AI Log {self.id} by {self.user_id} @ {self.created_at:%Y-%m-%d %H:%M:%S}"


class RoomRating(models.Model):
    """방장 평점 모델
    - 참여자가 방장에게 평점을 남기는 모델
    - 한 방에 대해 한 참여자는 한 번만 평점을 남길 수 있음
    """
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='ratings')
    rater = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings_given')
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings_received')
    rating = models.FloatField()  # 0.0 ~ 5.0 (0.5 단위)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('room', 'rater', 'host')  # 한 방에서 한 평가자는 같은 대상에게 한 번만 평점 가능
        indexes = [
            models.Index(fields=['room', 'rater']),
            models.Index(fields=['host']),
        ]

    def __str__(self) -> str:
        return f"{self.rater.username} -> {self.host.username} ({self.rating}/5.0) in Room {self.room.id}"
