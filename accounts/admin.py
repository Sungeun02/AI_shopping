from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Room, RoomParticipant, ChatMessage, AiRecommendLog


class CustomUserAdmin(UserAdmin):
    model = User
    # User 모델에서 제거된 필드들 제외
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Additional Info', {'fields': ('name', 'age', 'gender', 'phone', 'trust_score', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'name'),
        }),
    )
    readonly_fields = ('created_at', 'updated_at', 'date_joined', 'last_login')
    list_display = ('username', 'name', 'is_staff', 'is_active', 'trust_score', 'created_at')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'gender')
    search_fields = ('username', 'name')
    
    def has_delete_permission(self, request, obj=None):
        """슈퍼유저는 삭제 권한 있음"""
        return request.user.is_superuser


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'mart_name', 'meetup_at', 'status', 'created_by', 'host_trust_score', 'current_participants_cached')
    search_fields = ('mart_name',)
    list_filter = ('status', 'created_at')
    actions = ['delete_selected']
    
    def has_delete_permission(self, request, obj=None):
        """슈퍼유저는 삭제 권한 있음"""
        return request.user.is_superuser


@admin.register(RoomParticipant)
class RoomParticipantAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'joined_at')
    
    def has_delete_permission(self, request, obj=None):
        """슈퍼유저는 삭제 권한 있음"""
        return request.user.is_superuser


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'created_at')
    
    def has_delete_permission(self, request, obj=None):
        """슈퍼유저는 삭제 권한 있음"""
        return request.user.is_superuser


@admin.register(AiRecommendLog)
class AiRecommendLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'lat', 'lng')
    list_filter = ('user', 'created_at')
    search_fields = ('user__username',)
    
    def has_delete_permission(self, request, obj=None):
        """슈퍼유저는 삭제 권한 있음"""
        return request.user.is_superuser


admin.site.register(User, CustomUserAdmin)
