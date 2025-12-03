from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    # rooms/actions
    path('rooms/create/', views.create_room, name='create_room'),
    path('rooms/<int:room_id>/join/', views.join_room, name='join_room'),
    path('rooms/<int:room_id>/leave/', views.leave_room, name='leave_room'),
    path('rooms/<int:room_id>/delete/', views.delete_room, name='delete_room'),
    path('rooms/<int:room_id>/mark-done/', views.mark_room_done, name='mark_room_done'),
    path('rooms/recommend/', views.ai_recommend, name='ai_recommend'),
    path('api/nearby_marts/', views.nearby_marts, name='nearby_marts'),
    path('api/mart-suggest/', views.mart_suggest, name='mart_suggest'),
    path('api/geocode/', views.geocode, name='geocode'),
    # chat
    path('chat/', views.chat_list, name='chat_list'),
    path('chat/<int:room_id>/', views.chat_room, name='chat_room'),
    path('api/chat/<int:room_id>/messages/', views.get_new_messages, name='get_new_messages'),
    # notifications
    path('api/notifications/', views.get_notifications, name='get_notifications'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/unread-count/', views.get_unread_count, name='get_unread_count'),
    # settlement
    path('rooms/<int:room_id>/settlement/', views.process_settlement, name='process_settlement'),
    path('rooms/<int:room_id>/settlement-finalize/', views.finalize_settlement, name='finalize_settlement'),
    path('api/rooms/<int:room_id>/settlement-result/', views.get_settlement_result, name='get_settlement_result'),
    # rating
    path('api/rooms/<int:room_id>/rating/', views.submit_rating, name='submit_rating'),
    path('api/rooms/<int:room_id>/rating-status/', views.check_rating_status, name='check_rating_status'),
]
