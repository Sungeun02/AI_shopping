from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Room, RoomParticipant, ChatMessage, AiRecommendLog


class CustomUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('name', 'age', 'gender', 'phone', 'trust_score', 'created_at', 'updated_at')}),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'mart_name', 'meetup_at', 'status', 'created_by', 'host_trust_score', 'current_participants_cached')
    search_fields = ('mart_name',)


@admin.register(RoomParticipant)
class RoomParticipantAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'joined_at')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'created_at')


@admin.register(AiRecommendLog)
class AiRecommendLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'lat', 'lng')
    list_filter = ('user', 'created_at')
    search_fields = ('user__username',)


admin.site.register(User, CustomUserAdmin)
