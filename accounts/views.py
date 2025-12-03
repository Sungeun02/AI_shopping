from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.http import JsonResponse, HttpResponseBadRequest
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from django.db import transaction
from django.conf import settings
import requests
from decimal import Decimal, InvalidOperation
import logging as log
import os
import json
import time
import uuid
import re
from datetime import datetime, timedelta

# Optional AI/geo stack
try:
    import numpy as np
except Exception:
    np = None
try:
    from geopy.distance import geodesic
except Exception:
    geodesic = None
try:
    from pyproj import Transformer
except Exception:
    Transformer = None
try:
    from dateutil.parser import isoparse
except Exception:
    isoparse = None
try:
    import joblib
except Exception:
    joblib = None
try:
    import xgboost as xgb
except Exception:
    xgb = None
from .forms import CustomUserCreationForm
from .models import Room, RoomParticipant, ChatMessage, AiRecommendLog, Notification, RoomRating


def format_datetime_for_response(dt):
    """datetime을 ISO 형식 문자열로 반환 (이미 한국 시간이므로 변환 불필요)"""
    if dt is None:
        return None
    # USE_TZ = False이므로 이미 한국 시간으로 저장되어 있음
    if timezone.is_aware(dt):
        # 혹시 aware datetime이면 naive로 변환
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()

# ---- API keys (env) ----
KAKAO_DEFAULT_KEY = os.getenv('KAKAO_REST_API_KEY', '').strip()
SEOUL_API_KEY = os.getenv('SEOUL_API_KEY', '').strip()

# ---- AI model loading (lazy-safe) ----
XGB_MODEL = None
SCALER = None
if joblib:
    try:
        # Paths: 환경변수가 있으면 사용, 없으면 기본값 사용
        # Docker 컨테이너 내부 경로(/app/ml_models/...) 또는 호스트 상대 경로(ml_models/...)
        model_path_env = os.getenv('XGB_MODEL_PATH', '')
        scaler_path_env = os.getenv('SCALER_PATH', '')
        
        # 환경변수가 있으면 그대로 사용, 없으면 기본값 사용
        if model_path_env:
            model_path = model_path_env
        else:
            # 기본값: 먼저 v2 파일 확인, 없으면 기본 파일 확인
            if os.path.exists('ml_models/mart_recommender_v2.xgb'):
                model_path = 'ml_models/mart_recommender_v2.xgb'
            elif os.path.exists('mart_recommender_v2.xgb'):
                model_path = 'mart_recommender_v2.xgb'
            else:
                model_path = 'mart_recommender.xgb'
        
        if scaler_path_env:
            scaler_path = scaler_path_env
        else:
            # 기본값: 먼저 v2 파일 확인, 없으면 기본 파일 확인
            if os.path.exists('ml_models/recommender_scaler_v2.joblib'):
                scaler_path = 'ml_models/recommender_scaler_v2.joblib'
            elif os.path.exists('recommender_scaler_v2.joblib'):
                scaler_path = 'recommender_scaler_v2.joblib'
            else:
                scaler_path = 'recommender_scaler.joblib'
        
        log.info(f"Trying to load model from: {model_path}")
        log.info(f"Trying to load scaler from: {scaler_path}")
        
        if os.path.exists(model_path):
            loaded_model = None
            if model_path.lower().endswith('.xgb') and xgb is not None:
                try:
                    booster = xgb.Booster()
                    booster.load_model(model_path)
                    class _XGBWrapper:
                        def __init__(self, booster):
                            self.booster = booster
                        def predict_proba(self, X):
                            import numpy as _np
                            d = xgb.DMatrix(X)
                            p = self.booster.predict(d)
                            return _np.vstack([1 - p, p]).T
                    loaded_model = _XGBWrapper(booster)
                    log.info(f"Successfully loaded XGB model from {model_path}")
                except Exception as e:
                    log.warning(f"Native XGBoost load failed, trying joblib: {e}")
            if loaded_model is None:
                loaded_model = joblib.load(model_path)
                log.info(f"Successfully loaded model via joblib from {model_path}")
            XGB_MODEL = loaded_model
        else:
            log.warning(f"Model file not found: {model_path}")
        
        if os.path.exists(scaler_path):
            SCALER = joblib.load(scaler_path)
            log.info(f"Successfully loaded scaler from {scaler_path}")
        else:
            log.warning(f"Scaler file not found: {scaler_path}")
    except Exception as e:
        log.error(f"AI model load failed: {e}")
        import traceback
        log.error(traceback.format_exc())

# ---- EPSG transforms for Korea (TM → WGS84) ----
_EPSG_CANDIDATES = [
    'EPSG:5179',  # UTM-K
    'EPSG:5181',  # Korea 2000 / Unified CS
    'EPSG:5186',  # Korea 2000 / Central Belt
    'EPSG:2097',  # Korea West Belt (old)
    'EPSG:4326',  # WGS84 (identity)
]
_TRANSFORMERS = {}
if Transformer:
    for code in list(_EPSG_CANDIDATES):
        try:
            _TRANSFORMERS[code] = Transformer.from_crs(code, 'EPSG:4326', always_xy=True)
        except Exception:
            pass


def home_view(request):
    """랜딩 페이지: 시작하기 → 로그인"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    return render(request, 'home.html')


@login_required
def profile_view(request):
    """회원 정보 페이지"""
    return render(request, 'accounts/profile.html', { 'user': request.user })


@login_required
def update_profile(request):
    """회원정보 수정"""
    if request.method == 'POST':
        from .forms import UserProfileUpdateForm
        form = UserProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, '회원정보가 수정되었습니다.')
            return redirect('accounts:profile')
        else:
            messages.error(request, '회원정보 수정에 실패했습니다. 입력한 정보를 확인해주세요.')
    else:
        from .forms import UserProfileUpdateForm
        form = UserProfileUpdateForm(instance=request.user)
    
    return render(request, 'accounts/profile.html', {
        'user': request.user,
        'form': form,
        'is_editing': True
    })


def login_view(request):
    """로그인 뷰"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'안녕하세요, {user.name}님!')
            return redirect('accounts:dashboard')
        else:
            messages.error(request, '아이디 또는 비밀번호가 올바르지 않습니다.')
    
    return render(request, 'accounts/login.html')


@login_required
def logout_view(request):
    """로그아웃 뷰"""
    logout(request)
    messages.info(request, '로그아웃되었습니다.')
    return redirect('accounts:login')


@login_required
@ensure_csrf_cookie
def dashboard_view(request):
    """대시보드 뷰: 팀 찾기/채팅 탭, 필터/정렬, 알림/즐겨찾기"""
    # 필터 파라미터
    q_date = request.GET.get('date')
    q_mart = request.GET.get('mart')
    q_status = request.GET.get('status')  # RECRUITING/FULL/DONE
    sort = request.GET.get('sort', 'soon')  # soon, latest, popular

    rooms = Room.objects.all().select_related('created_by').annotate(num_participants=Count('participants'))
    
    # 시간이 지났거나 약속 시간 10분 전 이내인 방은 제외
    from datetime import timedelta
    now = timezone.now()
    cutoff_time = now + timedelta(minutes=10)
    rooms = rooms.filter(meetup_at__gt=cutoff_time)
    
    # 팀 찾기에서는 모집 완료된 방(STATUS_FULL, STATUS_DONE)은 제외 (참여 가능한 방만 표시)
    rooms = rooms.exclude(status__in=[Room.STATUS_DONE, Room.STATUS_FULL])
    
    if q_date:
        try:
            day = timezone.datetime.fromisoformat(q_date)
            rooms = rooms.filter(meetup_at__date=day.date())
        except Exception:
            pass
    if q_mart:
        rooms = rooms.filter(mart_name__icontains=q_mart)
    if q_status:
        rooms = rooms.filter(status=q_status)

    if sort == 'latest':
        rooms = rooms.order_by('-created_at')
    elif sort == 'popular':
        rooms = rooms.order_by('-num_participants', 'meetup_at')
    else:
        rooms = rooms.order_by('meetup_at')

    my_rooms = Room.objects.filter(participants__user=request.user)
    # 사용자가 참여한 방 ID 목록
    my_room_ids = set(my_rooms.values_list('id', flat=True))
    
    # my_rooms에 카테고리 이름 추가
    my_rooms_with_categories = []
    for room in my_rooms:
        room_dict = {
            'room': room,
            'category_names': [Room.CATEGORY_MAP.get(c, str(c)) for c in (room.categories or [])],
        }
        my_rooms_with_categories.append(room_dict)
    
    return render(request, 'accounts/dashboard.html', {
        'user': request.user,
        'rooms': rooms,
        'my_rooms': my_rooms,
        'my_rooms_with_categories': my_rooms_with_categories,
        'my_room_ids': my_room_ids,
    })


@login_required
def create_room(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    mart = request.POST.get('mart')
    meetup_at = request.POST.get('meetup_at')  # ISO string
    max_p_raw = request.POST.get('max_participants', '4')
    # optional location fields
    road_address = (request.POST.get('road_address') or request.POST.get('addr') or '').strip()
    x_raw = request.POST.get('x') or request.POST.get('X')
    y_raw = request.POST.get('y') or request.POST.get('Y')
    # 필수 필드 검증
    if not mart or not mart.strip():
        return JsonResponse({'ok': False, 'error': 'MISSING_FIELDS', 'message': '조건을 모두 입력하지 않았습니다'}, status=400)
    if not meetup_at:
        return JsonResponse({'ok': False, 'error': 'MISSING_FIELDS', 'message': '조건을 모두 입력하지 않았습니다'}, status=400)
    try:
        max_p = int(max_p_raw)
        if max_p < 2 or max_p > 10:
            return JsonResponse({'ok': False, 'error': 'BAD_MAX'}, status=400)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'BAD_MAX'}, status=400)
    # parse datetime robustly
    # 프론트엔드에서 보낸 시간은 한국 시간으로 가정하고 naive datetime으로 저장
    try:
        # ISO 형식 문자열 파싱 시도 (예: "2025-11-22T22:00:00" 또는 "2025-11-22T22:00:00+09:00")
        if 'T' in meetup_at or '+' in meetup_at or 'Z' in meetup_at:
            # ISO 형식
            dt_str = meetup_at.replace('Z', '+00:00')
            dt = datetime.fromisoformat(dt_str)
            # timezone 정보가 있으면 한국 시간으로 변환 후 naive로 변환
            if timezone.is_aware(dt):
                from django.utils import timezone as tz_util
                seoul_tz = tz_util.get_fixed_timezone(540)  # UTC+9 (Asia/Seoul)
                dt = dt.astimezone(seoul_tz).replace(tzinfo=None)
        else:
            # ISO 형식이 아닌 경우 (예: "2025-11-22 22:00:00" 또는 "2025-11-22 22:00")
            try:
                dt = datetime.strptime(meetup_at, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(meetup_at, '%Y-%m-%d %H:%M')
            # 이미 naive datetime이므로 그대로 사용
    except Exception as e:
        log.error(f"DateTime parsing error: {e}, input: {meetup_at}")
        return JsonResponse({'ok': False, 'error': 'BAD_DATETIME', 'message': f'시간 형식 오류: {str(e)}'}, status=400)
    
    # 과거 날짜/시간 검증 (한국 시간 기준)
    now = timezone.now().replace(tzinfo=None) if timezone.is_aware(timezone.now()) else timezone.now()
    if dt <= now:
        return JsonResponse({'ok': False, 'error': 'PAST_DATETIME', 'message': '이미 지난 날짜와 시간은 선택할 수 없습니다'}, status=400)

    # parse coordinates safely
    x_val = None
    y_val = None
    try:
        if x_raw not in (None, ''):
            x_val = Decimal(str(x_raw))
    except (InvalidOperation, ValueError):
        x_val = None
    try:
        if y_raw not in (None, ''):
            y_val = Decimal(str(y_raw))
    except (InvalidOperation, ValueError):
        y_val = None

    # categories (multi): accept numeric codes or legacy names, store as codes
    cats = request.POST.getlist('categories')
    if not cats:
        raw = (request.POST.get('categories') or '').strip()
        if raw:
            cats = [c.strip() for c in raw.split(',') if c.strip()]
    categories = []
    name_to_code = {v: k for k, v in Room.CATEGORY_MAP.items()}
    for c in cats:
        try:
            code = int(c)
        except Exception:
            code = name_to_code.get(c)
        if code in Room.CATEGORY_MAP:
            categories.append(code)
    
    # 카테고리 최소 1개 선택 검증
    if not categories or len(categories) == 0:
        return JsonResponse({'ok': False, 'error': 'NO_CATEGORIES', 'message': '카테고리를 최소 하나 선택해주세요'}, status=400)

    room = Room.objects.create(
        mart_name=mart,
        meetup_at=dt,
        max_participants=max_p,
        created_by=request.user,
        road_address=road_address,
        x=x_val,
        y=y_val,
        categories=categories,
        host_trust_score=float(getattr(request.user, 'trust_score', 3.0) or 3.0),
        current_participants_cached=1,
    )
    RoomParticipant.objects.create(room=room, user=request.user)
    room.update_status()
    
    return JsonResponse({
        'ok': True,
        'room': {
            'id': room.id,
            'mart': room.mart_name,
            'meetup_at': format_datetime_for_response(room.meetup_at),
            'current': room.current_participants,
            'max': room.max_participants,
            'status': room.status,
            'status_text': room.get_status_display(),
            'road_address': room.road_address,
            'x': str(room.x) if room.x is not None else None,
            'y': str(room.y) if room.y is not None else None,
            'categories': room.categories,
            'host_name': request.user.name,
            'host_trust_score': round(float(request.user.trust_score), 1),
        }
    })


@login_required
@transaction.atomic
def join_room(request, room_id: int):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    try:
        room = Room.objects.select_for_update().get(id=room_id)
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)

    # 시간 검증: 약속 시간이 지났거나 10분 전 이내면 참여 불가
    from datetime import timedelta
    now = timezone.now()
    cutoff_time = room.meetup_at - timedelta(minutes=10)
    if now >= cutoff_time:
        room.update_status()
        return JsonResponse({'ok': False, 'error': 'TIME_EXPIRED', 'message': '약속 시간이 지났거나 10분 전 이내입니다'}, status=400)

    # 모집완료된 방(STATUS_FULL)은 참여 불가
    if room.status == Room.STATUS_FULL:
        return JsonResponse({'ok': False, 'error': 'ROOM_FULL', 'message': '모집이 완료된 방입니다'}, status=400)

    if not room.is_joinable():
        room.update_status()
        return JsonResponse({'ok': False, 'status': room.status})

    obj, created = RoomParticipant.objects.get_or_create(room=room, user=request.user)
    if created:
        # 시그널이 자동으로 current_participants_cached를 업데이트함
        # 시스템 메시지 생성
        ChatMessage.objects.create(
            room=room,
            user=None,
            content=f'{request.user.name}님이 들어왔습니다',
            is_system=True
        )
        # 방장에게 알림 생성
        if room.created_by != request.user:
            Notification.objects.create(
                user=room.created_by,
                room=room,
                notification_type=Notification.TYPE_JOIN,
                message=f'{request.user.name}님이 참여했습니다'
            )
        # 다른 참여자들에게도 알림
        other_participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user).exclude(user=room.created_by)
        for participant in other_participants:
            Notification.objects.create(
                user=participant.user,
                room=room,
                notification_type=Notification.TYPE_JOIN,
                message=f'{request.user.name}님이 참여했습니다'
            )
    room.update_status()
    return JsonResponse({
        'ok': True,
        'current': room.current_participants,
        'max': room.max_participants,
        'status': room.status,
        'status_text': '정산완료' if room.settlement_result else room.get_status_display(),
        'settlement_result': bool(room.settlement_result),
    })


@login_required
def finalize_settlement(request, room_id: int):
    """방장이 정산 배분 결과를 최종 확정한다.
    Body(JSON): {
        items: [{ name, count, price: { unitPrice, price }, assignedUserIds: [int, ...] }, ...],
        per_user: { userId: amount, ... },
        total: int
    }
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)

    if room.created_by != request.user:
        return JsonResponse({'ok': False, 'error': 'NOT_OWNER'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'BAD_JSON'}, status=400)

    items = payload.get('items') or []
    per_user = payload.get('per_user') or {}
    total = int(payload.get('total') or 0)

    # Minimal validation
    if not isinstance(items, list) or not isinstance(per_user, dict):
        return JsonResponse({'ok': False, 'error': 'BAD_PAYLOAD'}, status=400)

    # Save into settlement_result (dict)
    base = room.settlement_result if isinstance(room.settlement_result, dict) else {'texts': (room.settlement_result or [])}
    base['allocation'] = {
        'items': items,
        'per_user': per_user,
        'total': total,
        'finalized_by': request.user.id,
        'finalized_at': timezone.now().isoformat(),
    }
    room.settlement_result = base
    room.settlement_created_at = timezone.now()
    room.save()

    # System message + notifications
    ChatMessage.objects.create(
        room=room,
        user=None,
        content=f'{request.user.name} 방장이 정산을 완료했습니다',
        is_system=True
    )
    participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user)
    for participant in participants:
        Notification.objects.create(
            user=participant.user,
            room=room,
            notification_type=Notification.TYPE_CHAT,
            message=f'{request.user.name} 방장이 정산을 완료했습니다. 결과를 확인하세요.'
        )

    return JsonResponse({'ok': True})


# 즐겨찾기 기능 제거


@login_required
def ai_recommend(request):
    """간단한 AI 추천 더미: 신뢰도 점수와 가까운 시간 순으로 상위 3개 나중ㅇ 아예 수정할 예정정"""
    now = timezone.now()
    # 시간이 지났거나 약속 시간 10분 전 이내인 방은 제외
    # AI 추천에서는 모집중 상태만 표시 (모집완료된 방은 제외)
    from datetime import timedelta
    cutoff_time = now + timedelta(minutes=10)
    rooms = (Room.objects.filter(status=Room.STATUS_RECRUITING, meetup_at__gt=cutoff_time)
             .annotate(num_participants=Count('participants'))
             .order_by('meetup_at')[:20])
    top = [
        {
            'id': r.id,
            'mart': r.mart_name,
            'meetup_at': format_datetime_for_response(r.meetup_at),
            'current': r.current_participants,
            'max': r.max_participants,
        } for r in rooms[:3]
    ]
    return JsonResponse({'ok': True, 'results': top})


@login_required
def chat_list(request):
    my_rooms = Room.objects.filter(participants__user=request.user).order_by('meetup_at')
    return render(request, 'accounts/chat_list.html', { 'rooms': my_rooms })


@login_required
def chat_room(request, room_id: int):
    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        from django.contrib import messages
        messages.error(request, '방을 찾을 수 없습니다.')
        return redirect('accounts:dashboard')
    
    # 사용자가 방에 참여했는지 확인 (방장은 자동으로 참여자로 간주)
    is_participant = RoomParticipant.objects.filter(room=room, user=request.user).exists()
    if not is_participant and room.created_by != request.user:
        from django.contrib import messages
        messages.error(request, '이 방에 참여할 권한이 없습니다.')
        return redirect('accounts:dashboard')
    
    messages_qs = ChatMessage.objects.filter(room=room).select_related('user')
    # participants for settlement UI
    parts = RoomParticipant.objects.filter(room=room).select_related('user')
    participants = [
        {
            'id': p.user.id,
            'name': p.user.name,
            'username': p.user.username,
        }
        for p in parts
    ]
    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            msg = ChatMessage.objects.create(room=room, user=request.user, content=content)
            # 다른 참여자들에게 알림 생성
            participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user)
            for participant in participants:
                Notification.objects.create(
                    user=participant.user,
                    room=room,
                    notification_type=Notification.TYPE_CHAT,
                    message=f'{request.user.name}님이 메시지를 보냈습니다: {content[:50]}'
                )
            # JSON 응답 반환
            return JsonResponse({
                'ok': True,
                'message': {
                    'id': msg.id,
                    'user': request.user.name,
                    'user_id': request.user.id,
                    'content': msg.content,
                    'created_at': msg.created_at.isoformat(),
                    'is_system': msg.is_system,
                }
            })
    return render(request, 'accounts/chat_room.html', {
        'room': room,
        'chat_messages': messages_qs,
        'participants_json': json.dumps(participants, ensure_ascii=False),
    })


@login_required
def get_new_messages(request, room_id: int):
    """새로운 채팅 메시지 가져오기 (Polling용)"""
    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Room not found'}, status=404)
    
    # 사용자가 방에 참여했는지 확인
    is_participant = RoomParticipant.objects.filter(room=room, user=request.user).exists()
    if not is_participant and room.created_by != request.user:
        return JsonResponse({'ok': False, 'error': 'No permission'}, status=403)
    
    # 마지막 메시지 ID (쿼리 파라미터에서 가져오기)
    last_message_id = request.GET.get('last_id', 0)
    try:
        last_message_id = int(last_message_id)
    except (ValueError, TypeError):
        last_message_id = 0
    
    # 마지막 메시지 ID 이후의 새 메시지들 가져오기
    new_messages = ChatMessage.objects.filter(
        room=room,
        id__gt=last_message_id
    ).select_related('user').order_by('created_at')
    
    messages_data = []
    max_id = last_message_id
    for msg in new_messages:
        messages_data.append({
            'id': msg.id,
            'user': msg.user.name,
            'user_id': msg.user.id,
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
            'is_system': msg.is_system,
        })
        if msg.id > max_id:
            max_id = msg.id
    
    return JsonResponse({
        'ok': True,
        'messages': messages_data,
        'last_id': max_id,
    })


@login_required
def leave_room(request, room_id: int):
    """채팅방 나가기"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    
    try:
        room = Room.objects.get(id=room_id)
        participant = RoomParticipant.objects.get(room=room, user=request.user)
        
        # 방장이 나가는 경우
        if room.created_by == request.user:
            # 다른 참여자가 있으면 첫 번째 참여자를 방장으로 변경
            other_participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user).first()
            if other_participants:
                room.created_by = other_participants.user
                # update host trust score as owner changed
                try:
                    room.host_trust_score = float(getattr(other_participants.user, 'trust_score', 3.0) or 3.0)
                except Exception:
                    room.host_trust_score = 3.0
                room.save(update_fields=['created_by', 'host_trust_score'])
        
        participant.delete()
        # 시그널이 자동으로 current_participants_cached를 업데이트함
        # 시스템 메시지 생성
        ChatMessage.objects.create(
            room=room,
            user=None,
            content=f'{request.user.name}님이 나갔습니다',
            is_system=True
        )
        # 방장에게 알림 생성
        if room.created_by != request.user:
            Notification.objects.create(
                user=room.created_by,
                room=room,
                notification_type=Notification.TYPE_LEAVE,
                message=f'{request.user.name}님이 나갔습니다'
            )
        # 다른 참여자들에게도 알림
        other_participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user).exclude(user=room.created_by)
        for participant in other_participants:
            Notification.objects.create(
                user=participant.user,
                room=room,
                notification_type=Notification.TYPE_LEAVE,
                message=f'{request.user.name}님이 나갔습니다'
            )
        room.update_status()
        
        return JsonResponse({'ok': True})
    except (Room.DoesNotExist, RoomParticipant.DoesNotExist):
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)


@login_required
def delete_room(request, room_id: int):
    """내가 만든 채팅방 삭제 (방장만 가능)"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    
    try:
        room = Room.objects.get(id=room_id)
        
        # 방장인지 확인
        if room.created_by != request.user:
            return JsonResponse({'ok': False, 'error': 'NOT_OWNER'}, status=403)
        
        # 방 삭제 전에 참여자들에게 알림 생성
        participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user)
        room_mart_name = room.mart_name  # 방 삭제 전에 마트 이름 저장
        for participant in participants:
            Notification.objects.create(
                user=participant.user,
                room=room,  # 방 삭제 전이므로 room 참조 가능
                notification_type=Notification.TYPE_DELETE,
                message=f'{request.user.name} 방장이 방을 삭제하셨습니다.',
                deleted_room_name=room_mart_name  # 삭제된 방의 마트 이름 저장
            )
        
        room.delete()
        return JsonResponse({'ok': True})
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)


@login_required
def mark_room_done(request, room_id: int):
    """모집 완료/모집중 상태 토글 (방장만 가능)"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    
    try:
        room = Room.objects.get(id=room_id)
        
        # 방장인지 확인
        if room.created_by != request.user:
            return JsonResponse({'ok': False, 'error': 'NOT_OWNER'}, status=403)
        
        # 시간 검증: 약속 시간이 지났거나 10분 전 이내면 변경 금지
        from datetime import timedelta
        now = timezone.now()
        cutoff_time = room.meetup_at - timedelta(minutes=10)
        if now >= cutoff_time:
            return JsonResponse({
                'ok': False, 
                'error': 'TIME_EXPIRED', 
                'message': '약속 시간이 지났거나 10분 전 이내입니다. 상태를 변경할 수 없습니다.'
            }, status=400)
        
        # 상태 토글: 모집중 <-> 모집 완료
        if room.status == Room.STATUS_DONE:
            # 모집 완료 -> 모집중으로 변경
            room.status = Room.STATUS_RECRUITING
            room.save()
            # 시스템 메시지 생성
            ChatMessage.objects.create(
                room=room,
                user=None,
                content=f'{room.created_by.name}방장이 다시 모집중으로 변경하였습니다',
                is_system=True
            )
            # 참여자들에게 알림 생성
            participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user)
            for participant in participants:
                Notification.objects.create(
                    user=participant.user,
                    room=room,
                    notification_type=Notification.TYPE_DONE,
                    message=f'{room.created_by.name}방장이 다시 모집중으로 변경하였습니다'
                )
            return JsonResponse({'ok': True, 'status': room.status, 'status_text': room.get_status_display()})
        else:
            # 모집중 -> 모집 완료로 변경
            room.status = Room.STATUS_DONE
            room.save()
            # 시스템 메시지 생성
            ChatMessage.objects.create(
                room=room,
                user=None,
                content=f'{room.created_by.name}방장이 모집을 마감했습니다',
                is_system=True
            )
            # 참여자들에게 알림 생성
            participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user)
            for participant in participants:
                Notification.objects.create(
                    user=participant.user,
                    room=room,
                    notification_type=Notification.TYPE_DONE,
                    message=f'{room.created_by.name}방장이 모집을 완료했습니다'
                )
            
            return JsonResponse({'ok': True, 'status': room.status, 'status_text': room.get_status_display()})
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)


@login_required
def mart_suggest(request):
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'results': []})

    url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/LOCALDATA_082501/1/1000/"

    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()

        rows = (data.get('LOCALDATA_082501') or {}).get('row', [])
        q_lower = q.lower()
        filtered = []

        for item in rows:
            name = (item.get('BPLCNM') or '')
            addr = (item.get('RDNWHLADDR') or '')
            post = (item.get('RDNPOSTNO') or '')

            if (q_lower in name.lower()) or (q_lower in addr.lower()) or (q_lower in post.lower()):
                filtered.append({
                    'name': name,
                    'addr': addr,
                    'post': post,
                    'x': item.get('X'),
                    'y': item.get('Y'),
                })

            if len(filtered) >= 10:
                break

        return JsonResponse({'results': filtered})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)



# ---- Kakao geocoding helpers ----
def _get_kakao_key(request):
    key = (request.GET.get("kakao_key") or "").strip()
    if key:
        return key
    return KAKAO_DEFAULT_KEY


def _geocode_kakao(query: str, kakao_key: str):
    """문자열 주소(query) → (lat, lon, road_address or None), 실패 시 None"""
    if not kakao_key:
        return None
    try:
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {kakao_key}"}
        params = {"query": query}
        r = requests.get(url, headers=headers, params=params, timeout=5)
        r.raise_for_status()
        docs = r.json().get("documents", [])
        if not docs:
            return None
        doc = docs[0]
        lon = float(doc["x"]); lat = float(doc["y"])  # Kakao: x=lon, y=lat
        road_addr = (doc.get("road_address") or {}).get("address_name") or \
                    (doc.get("address") or {}).get("address_name")
        return (lat, lon, road_addr)
    except Exception as e:
        log.exception("kakao geocode error: %s", e)
        return None


@require_GET
def geocode(request):
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'error': 'query required'}, status=400)
    kakao_key = _get_kakao_key(request)
    result = _geocode_kakao(q, kakao_key)
    if not result:
        return JsonResponse({'error': 'not found'}, status=404)
    lat, lon, road = result
    return JsonResponse({'ok': True, 'lat': lat, 'lng': lon, 'road_address': road})


class SignUpView(CreateView):
    """회원가입 뷰"""
    form_class = CustomUserCreationForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('accounts:login')
    
    def form_valid(self, form):
        messages.success(self.request, '회원가입이 완료되었습니다. 로그인해주세요.')
        return super().form_valid(form)


# --- GEO/AI helpers ---

def _in_korea(lat: float, lon: float) -> bool:
    return 33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.5

def _clean_num(v):
    if v is None:
        return None
    s = str(v).strip().replace(',', '')
    if not s or s.lower() == 'null':
        return None
    try:
        return float(s)
    except Exception:
        return None

def _tm_to_wgs84_with_epsg(x_raw, y_raw, epsg_code: str):
    if not Transformer:
        return None
    x = _clean_num(x_raw)
    y = _clean_num(y_raw)
    if x is None or y is None:
        return None
    try:
        T = _TRANSFORMERS.get(epsg_code)
        if not T:
            return None
        lon, lat = T.transform(x, y)
        return (lat, lon) if _in_korea(lat, lon) else None
    except Exception:
        return None

def _tm_to_wgs84_auto(x_raw, y_raw, my_lat, my_lon):
    if not Transformer or not geodesic:
        return None
    best = None
    my_pos = (my_lat, my_lon)
    for code in _EPSG_CANDIDATES:
        pair = _tm_to_wgs84_with_epsg(x_raw, y_raw, code)
        if not pair:
            continue
        lat, lon = pair
        d = geodesic(my_pos, (lat, lon)).km
        if (best is None) or (d < best[0]):
            best = (d, pair, code)
    if best:
        log.debug("AUTO-EPSG pick=%s d=%.3fkm", best[2], best[0])
        return best[1]
    return None

def _calculate_time_diff_hours(meetup_at, desired_time_iso: str) -> float:
    """방의 meetup_at과 사용자가 원하는 시간의 차이를 시간 단위로 계산
    
    Args:
        meetup_at: Room의 meetup_at (한국 시간으로 저장된 naive datetime)
        desired_time_iso: 사용자가 원하는 시간 (ISO 형식 문자열, 한국 시간)
                         프론트엔드에서 'Z'를 붙여서 보내지만 실제로는 한국 시간임
    
    Returns:
        시간 차이 (시간 단위)
    """
    if not isoparse:
        return 0.0
    try:
        # 프론트엔드에서 한국 시간을 'Z'를 붙여서 보내지만, 실제로는 한국 시간이므로
        # 'Z'를 제거하고 naive datetime으로 파싱
        desired_time_clean = desired_time_iso.replace('Z', '').replace('+00:00', '')
        
        # ISO 형식 파싱 시도
        try:
            # 'Z'를 제거한 후 파싱하면 naive datetime으로 파싱됨
            desired_dt = isoparse(desired_time_clean)
            # isoparse가 aware datetime을 반환할 수 있으므로 naive로 변환
            if timezone.is_aware(desired_dt):
                desired_dt = desired_dt.replace(tzinfo=None)
        except Exception:
            # ISO 파싱 실패 시 다른 형식 시도
            try:
                desired_dt = datetime.fromisoformat(desired_time_clean)
                if timezone.is_aware(desired_dt):
                    desired_dt = desired_dt.replace(tzinfo=None)
            except Exception:
                try:
                    desired_dt = datetime.strptime(desired_time_clean, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    desired_dt = datetime.strptime(desired_time_clean, '%Y-%m-%dT%H:%M:%S')
        
        # meetup_at도 naive datetime으로 확보
        if timezone.is_aware(meetup_at):
            meetup_dt = meetup_at.replace(tzinfo=None)
        else:
            meetup_dt = meetup_at
        
        # 둘 다 한국 시간(naive)이므로 직접 비교
        diff_seconds = abs((meetup_dt - desired_dt).total_seconds())
        return round(diff_seconds / 3600.0, 2)
    except Exception as e:
        log.warning(f"Time diff calculation error: {e}")
        return 24.0

def _calculate_jaccard_score(room_categories, user_categories: list) -> float:
    """카테고리 점수 계산: 교집합 / 방 카테고리 개수"""
    try:
        if not user_categories:
            return 0.0
        # Normalize both sides to strings (supports numeric codes or names)
        if isinstance(room_categories, str):
            set_room = set(c.strip() for c in room_categories.split(',') if c.strip())
        else:
            set_room = set(str(x) for x in (room_categories or []))
        set_user = set(str(x) for x in (user_categories or []))
        intersection = len(set_room.intersection(set_user))
        room_count = len(set_room)
        if room_count == 0:
            return 0.0
        return round(intersection / room_count, 3)
    except Exception as e:
        log.warning(f"Category score error: {e}")
        return 0.0

def _get_current_participants(room_id) -> int:
    try:
        room = Room.objects.only('current_participants_cached').get(id=room_id)
        return int(room.current_participants_cached)
    except Exception as e:
        try:
            return RoomParticipant.objects.filter(room_id=room_id).count()
        except Exception:
            log.error(f"Could not query RoomParticipant: {e}")
            return 0

def _get_store_reliability(room_id) -> float:
    """Return host trust score cached on Room.
    Falls back to 0.0 if unavailable.
    """
    try:
        room = Room.objects.only('host_trust_score').get(id=room_id)
        return round(float(room.host_trust_score or 0.0), 1)
    except Exception as e:
        log.error(f"Could not read host_trust_score for room {room_id}: {e}")
        return 0.0


@require_GET
def nearby_marts(request):
    if XGB_MODEL is None or SCALER is None or geodesic is None:
        missing = []
        if XGB_MODEL is None:
            missing.append('XGB_MODEL')
        if SCALER is None:
            missing.append('SCALER')
        if geodesic is None:
            missing.append('geodesic')
        return JsonResponse({"error": "AI components not loaded", "missing": missing}, status=500)
    try:
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        desired_time_iso = request.GET.get('desired_time')
        categories_str = request.GET.get('categories', '')
        if not lat or not lng or not desired_time_iso:
            return JsonResponse({"error": "lat, lng, desired_time are required"}, status=400)
        
        # desired_time 파싱 및 과거 날짜/시간 검증
        # 프론트엔드에서 한국 시간을 'Z'를 붙여서 보내지만, 실제로는 한국 시간이므로
        # 'Z'를 제거하고 naive datetime으로 파싱
        from datetime import timedelta  # 함수 시작 부분에서 import
        desired_time_clean = desired_time_iso.replace('Z', '').replace('+00:00', '')
        try:
            if isoparse:
                desired_dt = isoparse(desired_time_clean)
                # isoparse가 aware datetime을 반환할 수 있으므로 naive로 변환
                if timezone.is_aware(desired_dt):
                    desired_dt = desired_dt.replace(tzinfo=None)
            else:
                desired_dt = datetime.fromisoformat(desired_time_clean)
                if timezone.is_aware(desired_dt):
                    desired_dt = desired_dt.replace(tzinfo=None)
        except Exception:
            try:
                desired_dt = datetime.strptime(desired_time_clean, '%Y-%m-%d %H:%M:%S')
            except Exception:
                try:
                    desired_dt = datetime.strptime(desired_time_clean, '%Y-%m-%dT%H:%M:%S')
                except Exception:
                    return JsonResponse({'ok': False, 'error': 'BAD_DATETIME', 'message': '잘못된 날짜/시간 형식입니다'}, status=400)
        
        # 이미 한국 시간(naive datetime)으로 처리됨
        
        # 과거 날짜/시간 검증
        now = timezone.now()
        if desired_dt <= now:
            return JsonResponse({'ok': False, 'error': 'PAST_DATETIME', 'message': '이미 지난 날짜와 시간은 선택할 수 없습니다'}, status=400)
        
        my_lat = float(lat); my_lon = float(lng)
        if not _in_korea(my_lat, my_lon):
            return JsonResponse({"error": "lat/lng outside Korea"}, status=400)
        user_categories = [c.strip() for c in categories_str.split(',') if c.strip()]
        limit = int(request.GET.get('limit', 10))
        candidate_limit = max(30, limit * 3)

        # Stage 1: gather nearby recruiting rooms
        my_pos = (my_lat, my_lon)
        candidates = []
        # 시간이 지났거나 약속 시간 10분 전 이내인 방은 제외
        # timedelta는 이미 위에서 import됨
        now = timezone.now()
        cutoff_time = now + timedelta(minutes=10)
        
        # 사용자가 이미 참여한 방 ID 목록
        my_room_ids = set()
        if request.user.is_authenticated:
            my_room_ids = set(RoomParticipant.objects.filter(user=request.user).values_list('room_id', flat=True))
        
        # AI 추천에서는 모집중 상태만 표시 (모집완료된 방은 제외)
        qs = Room.objects.filter(status=Room.STATUS_RECRUITING, meetup_at__gt=cutoff_time).select_related('created_by')
        for room in qs:
            # 사용자가 이미 참여한 방은 제외
            if room.id in my_room_ids:
                continue
            # Try auto EPSG; if fails, try treating as WGS84 directly
            pair = _tm_to_wgs84_auto(room.x, room.y, my_lat, my_lon)
            if not pair and room.x is not None and room.y is not None:
                try:
                    # room.x (lon), room.y (lat)
                    if _in_korea(float(room.y), float(room.x)):
                        pair = (float(room.y), float(room.x))
                except Exception:
                    pass
            if not pair:
                continue
            room_lat, room_lon = pair
            d_km = geodesic(my_pos, (room_lat, room_lon)).km
            if d_km > 8.0:
                continue
            candidates.append({
                'room': room,
                'distance_km': d_km,
                'lat': round(room_lat, 6),
                'lng': round(room_lon, 6),
            })
        candidates.sort(key=lambda c: c['distance_km'])
        top_candidates = candidates[:candidate_limit]
        if not top_candidates:
            return JsonResponse({
                'ok': True,
                'origin': {'lat': my_lat, 'lng': my_lon, 'source': 'ai_ranking'},
                'results': [],
                'reason': 'No nearby rooms within 8km',
            })

        # Stage 2: feature build
        feature_vectors = []
        for c in top_candidates:
            room = c['room']
            f1 = c['distance_km']  # 거리
            f2 = _calculate_time_diff_hours(room.meetup_at, desired_time_iso)  # 시간 차이
            f3 = _calculate_jaccard_score(room.categories, user_categories)  # 카테고리 유사도
            f4 = _get_current_participants(room.id)  # 현재 참여 인원 수
            f5 = _get_store_reliability(room.id)  # 호스트 신뢰도
            feature_vectors.append([f1, f2, f3, f4, f5])

        if not feature_vectors:
            return JsonResponse({
                'ok': True,
                'origin': {'lat': my_lat, 'lng': my_lon, 'source': 'ai_ranking'},
                'results': [],
                'reason': 'No candidates for feature building',
            })
        
        if np is None:
            return JsonResponse({"error": "numpy is not available"}, status=500)
        
        try:
            X = np.array(feature_vectors)
            if X.size == 0:
                return JsonResponse({
                    'ok': True,
                    'origin': {'lat': my_lat, 'lng': my_lon, 'source': 'ai_ranking'},
                    'results': [],
                    'reason': 'Empty feature array',
                })
            Xs = SCALER.transform(X)
            probs = XGB_MODEL.predict_proba(Xs)[:, 1]
        except Exception as e:
            log.error(f"Feature processing error: {e}")
            import traceback
            log.error(traceback.format_exc())
            return JsonResponse({"error": f"Feature processing failed: {str(e)}"}, status=500)

        results = []
        for i, c in enumerate(top_candidates):
            room = c['room']
            current = _get_current_participants(room.id)
            results.append({
                'id': room.id,
                'mart': room.mart_name,
                'meetup_at': format_datetime_for_response(room.meetup_at),
                'current': current,
                'max': room.max_participants,
                'status': room.status,
                'status_text': '정산완료' if room.settlement_result else room.get_status_display(),
                'road_address': room.road_address,
                'distance_km': round(float(c['distance_km']), 3),
                'lat': c['lat'],
                'lng': c['lng'],
                'score': round(float(probs[i]), 4),
                'categories': room.categories,
                'host_name': room.created_by.name if room.created_by else None,
                'host_trust_score': float(room.created_by.trust_score) if room.created_by else 0.0,
                'settlement_result': bool(room.settlement_result),
            })
        results.sort(key=lambda r: r['score'], reverse=True)

        # Log the request
        try:
            desired_dt = isoparse(desired_time_iso) if isoparse else timezone.now()
            # USE_TZ = False이므로 이미 한국 시간(naive datetime)
            if timezone.is_aware(desired_dt):
                from django.utils import timezone as tz_util
                seoul_tz = tz_util.get_fixed_timezone(540)  # UTC+9 (Asia/Seoul)
                desired_dt = desired_dt.astimezone(seoul_tz).replace(tzinfo=None)
            name_to_code = {v: k for k, v in Room.CATEGORY_MAP.items()}
            cat_codes = []
            for c in user_categories:
                try:
                    code = int(c)
                except Exception:
                    code = name_to_code.get(c)
                if code in Room.CATEGORY_MAP:
                    cat_codes.append(code)
            top_results = [{"id": r['id'], "score": r['score']} for r in results[:limit]]
            AiRecommendLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                lat=my_lat,
                lng=my_lon,
                desired_time=desired_dt,
                categories=cat_codes,
                top_results=top_results,
            )
        except Exception as e:
            log.warning(f"Failed to log AI recommendation: {e}")

        return JsonResponse({
            'ok': True,
            'origin': {'lat': my_lat, 'lng': my_lon, 'source': 'ai_ranking'},
            'results': results[:limit],
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        log.exception("nearby_marts error: %s", e)
        log.error(f"Full traceback:\n{error_trace}")
        return JsonResponse({
            "error": error_msg,
            "details": error_trace.split('\n')[-5:] if error_trace else None  # Last 5 lines of traceback
        }, status=500)


@login_required
def get_notifications(request):
    """알림 목록 조회"""
    limit = int(request.GET.get('limit', 20))
    notifications = Notification.objects.filter(user=request.user).select_related('room').order_by('-created_at')[:limit]
    
    return JsonResponse({
        'ok': True,
        'notifications': [
            {
                'id': n.id,
                'type': n.notification_type,
                'message': n.message,
                'room_id': n.room.id if n.room else None,
                'room_name': n.room.mart_name if n.room else (n.deleted_room_name or '(삭제된 방)'),
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifications
        ]
    })


@login_required
def mark_notification_read(request, notification_id: int):
    """알림 읽음 처리"""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'ok': True})
    except Notification.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)


@login_required
def get_unread_count(request):
    """읽지 않은 알림 개수 조회"""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'ok': True, 'count': count})


@login_required
def process_settlement(request, room_id: int):
    """정산하기 - OCR 처리 (방장만 가능)"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    
    try:
        room = Room.objects.get(id=room_id)
        
        # 방장인지 확인
        if room.created_by != request.user:
            return JsonResponse({'ok': False, 'error': 'NOT_OWNER'}, status=403)
        
        if not request.FILES.get('image'):
            return JsonResponse({'ok': False, 'error': 'NO_IMAGE', 'message': '이미지를 업로드해주세요.'}, status=400)
        
        api_url = getattr(settings, 'OCR_API_URL', os.getenv("OCR_API_URL", ""))
        secret_key = getattr(settings, 'OCR_SECRET_KEY', os.getenv("OCR_SECRET_KEY", ""))
        
        if not api_url or not secret_key:
            return JsonResponse({
                'ok': False, 
                'error': 'OCR_CONFIG_MISSING', 
                'message': 'OCR 설정이 누락되었습니다. 환경변수 OCR_API_URL, OCR_SECRET_KEY를 설정하세요.'
            }, status=500)
        
        uploaded = request.FILES['image']
        request_json = {
            "images": [
                {
                    "format": "jpg",
                    "name": "demo",
                }
            ],
            "requestId": str(uuid.uuid4()),
            "version": "V2",
            "timestamp": int(round(time.time() * 1000)),
        }
        
        payload = {"message": json.dumps(request_json).encode("UTF-8")}
        files = [
            (
                "file",
                (
                    uploaded.name,
                    uploaded.read(),
                    getattr(uploaded, "content_type", "application/octet-stream"),
                ),
            )
        ]
        headers = {"X-OCR-SECRET": secret_key}
        
        try:
            resp = requests.post(
                api_url, headers=headers, data=payload, files=files, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            
            images = data.get("images") or []
            fields = (images[0].get("fields") if images else []) or []
            texts = [f.get("inferText", "") for f in fields if isinstance(f, dict)]
            ocr_texts = [t for t in texts if t]

            # --- Structured receipt parsing (Clova schema) ---
            def _get_text(node, key):
                try:
                    obj = node or {}
                    val = obj.get(key) or {}
                    return (val.get('text') if isinstance(val, dict) else '') or ''
                except Exception:
                    return ''

            def to_int(s):
                try:
                    raw = str(s or '').strip()
                    raw = re.sub(r'[^0-9]', '', raw)
                    return int(raw) if raw else 0
                except Exception:
                    return 0

            receipt = (images[0].get('receipt') if images else {}) or {}
            result = receipt.get('result') or {}
            sub_results = result.get('subResults') or []
            items = []
            if sub_results:
                for sr in sub_results:
                    if isinstance(sr, dict) and isinstance(sr.get('items'), list):
                        items = sr.get('items') or []
                        if items:
                            break
            if not items and isinstance(result.get('items'), list):
                items = result.get('items') or []

            structured_items = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                name_text = _get_text(it, 'name')
                count_text = _get_text(it, 'count')
                price_node = it.get('price') or {}
                unit_price_text = _get_text(price_node, 'unitPrice')
                line_price_text = _get_text(price_node, 'price')
                structured_items.append({
                    'name': name_text,
                    'count': to_int(count_text),
                    'price': {
                        'unitPrice': to_int(unit_price_text),
                        'price': to_int(line_price_text),
                    },
                })

            total_price_text = _get_text(result.get('totalPrice') or {}, 'price')
            receipt_struct = None
            if structured_items or total_price_text:
                receipt_struct = {
                    'items': structured_items,
                    'totalPrice': { 'price': to_int(total_price_text) },
                }
            
            # Some OCR responses may omit generic fields but include structured receipt.
            if not ocr_texts and not receipt_struct:
                return JsonResponse({
                    'ok': False, 
                    'error': 'NO_TEXT', 
                    'message': '인식된 텍스트가 없습니다.'
                }, status=400)
            
            # 정산 결과 저장 (texts + optional receipt)
            # 기존 결과가 있으면 유지하면서 texts와 receipt만 업데이트
            if isinstance(room.settlement_result, dict):
                base = room.settlement_result
            else:
                base = {'texts': (room.settlement_result or [])}
            
            base['texts'] = ocr_texts
            if receipt_struct:
                base['receipt'] = receipt_struct
            # allocation은 유지 (finalize_settlement에서 업데이트됨)
            
            room.settlement_result = base
            room.settlement_created_at = timezone.now()
            room.save()
            
            # 알림은 finalize_settlement에서만 생성 (중복 방지)
            
            return JsonResponse({
                'ok': True,
                'texts': ocr_texts,
                'receipt': receipt_struct,
                'message': '정산이 완료되었습니다.'
            })
            
        except requests.exceptions.RequestException as e:
            return JsonResponse({
                'ok': False, 
                'error': 'OCR_REQUEST_FAILED', 
                'message': f'OCR 요청 실패: {str(e)}'
            }, status=500)
        except Exception as e:
            return JsonResponse({
                'ok': False, 
                'error': 'OCR_ERROR', 
                'message': f'OCR 처리 중 오류가 발생했습니다: {str(e)}'
            }, status=500)
            
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)


@login_required
def get_settlement_result(request, room_id: int):
    """정산 결과 조회"""
    try:
        room = Room.objects.get(id=room_id)
        
        # 참여자 확인
        if not RoomParticipant.objects.filter(room=room, user=request.user).exists():
            return JsonResponse({'ok': False, 'error': 'NOT_PARTICIPANT'}, status=403)
        
        if not room.settlement_result:
            return JsonResponse({
                'ok': False, 
                'error': 'NO_RESULT', 
                'message': '정산 결과가 없습니다.'
            }, status=404)

        # settlement_result may be list (legacy) or dict ({texts, receipt, allocation})
        sr = room.settlement_result
        texts = []
        receipt = None
        allocation = None
        if isinstance(sr, list):
            texts = list(map(str, sr))
        elif isinstance(sr, dict):
            texts = list(map(str, sr.get('texts') or []))
            receipt = sr.get('receipt')
            allocation = sr.get('allocation')

        def _parse_total_amount(ocr_texts):
            """Extract a plausible total amount (KRW) from OCR lines.
            Strategy:
            1) Prefer lines containing total-related keywords.
            2) Extract all numeric candidates (with/without commas) and take the largest.
            3) Fallback to global largest numeric across all lines.
            """
            if not ocr_texts:
                return 0

            kw = (
                '합계', '총', '총액', '총금액', '결제', '받을', '금액', '합산', '결제금액', '청구금액', '지불'
            )
            amount_pattern = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,})")

            def extract_amounts(line):
                nums = []
                for m in amount_pattern.findall(line):
                    try:
                        n = int(m.replace(',', ''))
                        nums.append(n)
                    except Exception:
                        pass
                return nums

            # 1) keyword lines first
            keyword_lines = [t for t in ocr_texts if any(k in t for k in kw)]
            candidates = []
            for line in keyword_lines:
                candidates.extend(extract_amounts(line))

            # Heuristic: amounts under 1000 are likely item counts or small noise
            candidates = [n for n in candidates if n >= 1000]

            if candidates:
                return max(candidates)

            # 2) fallback to global max
            all_nums = []
            for line in ocr_texts:
                all_nums.extend(extract_amounts(line))
            all_nums = [n for n in all_nums if n >= 1000]
            return max(all_nums) if all_nums else 0

        total_amount = 0
        if receipt and isinstance(receipt, dict):
            try:
                total_amount = int(receipt.get('totalPrice', {}).get('price') or 0)
            except Exception:
                total_amount = 0
        if not total_amount:
            total_amount = _parse_total_amount(texts)
        participant_count = room.current_participants or RoomParticipant.objects.filter(room=room).count()
        per_person = 0
        if participant_count:
            # Round to nearest 10 won to avoid 1원 단위
            per_person_raw = total_amount / participant_count
            per_person = int(round(per_person_raw / 10.0) * 10)

        return JsonResponse({
            'ok': True,
            'texts': texts,
            'receipt': receipt,
            'allocation': allocation,
            'created_at': room.settlement_created_at.isoformat() if room.settlement_created_at else None,
            'summary': {
                'total_amount': total_amount,
                'participant_count': participant_count,
                'per_person_amount': per_person,
            }
        })
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)


@login_required
def submit_rating(request, room_id: int):
    """참여자 평점 남기기 (자신을 제외한 모든 참여자)"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    
    try:
        room = Room.objects.get(id=room_id)
        
        # 참여자 확인
        if not RoomParticipant.objects.filter(room=room, user=request.user).exists():
            return JsonResponse({'ok': False, 'error': 'NOT_PARTICIPANT'}, status=403)
        
        # 정산이 완료되어야 평점을 남길 수 있음
        if not room.settlement_result:
            return JsonResponse({'ok': False, 'error': 'NO_SETTLEMENT', 'message': '정산이 완료된 후 평점을 남길 수 있습니다.'}, status=400)
        
        # 대상 참여자 ID 확인
        try:
            target_user_id = int(request.POST.get('target_user_id', 0))
        except (ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'INVALID_TARGET', 'message': '올바른 대상 사용자를 선택해주세요.'}, status=400)
        
        if target_user_id == 0:
            return JsonResponse({'ok': False, 'error': 'INVALID_TARGET', 'message': '평점을 남길 참여자를 선택해주세요.'}, status=400)
        
        # 자신에게는 평점을 남길 수 없음
        if target_user_id == request.user.id:
            return JsonResponse({'ok': False, 'error': 'SELF_RATING', 'message': '자신에게는 평점을 남길 수 없습니다.'}, status=400)
        
        # 대상 사용자가 해당 방의 참여자인지 확인
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'USER_NOT_FOUND'}, status=404)
        
        if not RoomParticipant.objects.filter(room=room, user=target_user).exists():
            return JsonResponse({'ok': False, 'error': 'NOT_PARTICIPANT', 'message': '해당 사용자는 이 방의 참여자가 아닙니다.'}, status=400)
        
        # 이미 해당 참여자에게 평점을 남겼는지 확인
        if RoomRating.objects.filter(room=room, rater=request.user, host=target_user).exists():
            return JsonResponse({'ok': False, 'error': 'ALREADY_RATED', 'message': '이미 해당 참여자에게 평점을 남기셨습니다.'}, status=400)
        
        # 평점 값 확인
        try:
            rating = float(request.POST.get('rating', 0))
        except (ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'INVALID_RATING', 'message': '올바른 평점 값을 입력해주세요.'}, status=400)
        
        # 평점 범위 확인 (0.0 ~ 5.0, 0.5 단위)
        if rating < 0 or rating > 5:
            return JsonResponse({'ok': False, 'error': 'INVALID_RATING', 'message': '평점은 0.0 ~ 5.0 사이의 값이어야 합니다.'}, status=400)
        
        # 0.5 단위 확인
        if round(rating * 2) != rating * 2:
            return JsonResponse({'ok': False, 'error': 'INVALID_RATING', 'message': '평점은 0.5점 단위로 입력해주세요.'}, status=400)
        
        # 평점 저장
        with transaction.atomic():
            room_rating = RoomRating.objects.create(
                room=room,
                rater=request.user,
                host=target_user,
                rating=rating
            )
            
            # 대상 사용자의 trust_score 업데이트 (초기값 3.0을 포함한 모든 평점의 평균)
            all_ratings = RoomRating.objects.filter(host=target_user)
            rating_count = all_ratings.count()
            
            if rating_count > 0:
                # 모든 평점의 합계 계산
                total_rating = sum(r.rating for r in all_ratings)
                # 초기값 3.0을 포함하여 평균 계산 (평점 개수 + 1)
                avg_rating = (3.0 + total_rating) / (rating_count + 1)
            else:
                # 평점이 없으면 기본값 3.0 유지
                avg_rating = 3.0
            
            target_user.trust_score = round(avg_rating, 1)
            target_user.save(update_fields=['trust_score'])
            
            # 대상 사용자가 방장인 경우 Room의 host_trust_score도 업데이트
            if room.created_by == target_user:
                room.host_trust_score = target_user.trust_score
                room.save(update_fields=['host_trust_score'])
            
            # 대상 사용자가 만든 다른 Room들의 host_trust_score도 업데이트
            Room.objects.filter(created_by=target_user).update(host_trust_score=target_user.trust_score)
        
        return JsonResponse({
            'ok': True,
            'message': '평점이 등록되었습니다.',
            'rating': rating,
            'target_user_id': target_user_id,
            'target_trust_score': target_user.trust_score
        })
        
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)
    except Exception as e:
        log.error(f"Error submitting rating: {e}")
        return JsonResponse({'ok': False, 'error': 'SERVER_ERROR', 'message': '평점 등록 중 오류가 발생했습니다.'}, status=500)


@login_required
@require_GET
def check_rating_status(request, room_id: int):
    """평점 남기기 가능 여부 및 참여자 목록 확인"""
    try:
        room = Room.objects.get(id=room_id)
        
        # 참여자 확인
        if not RoomParticipant.objects.filter(room=room, user=request.user).exists():
            return JsonResponse({'ok': False, 'error': 'NOT_PARTICIPANT'}, status=403)
        
        # 정산이 완료되지 않았으면 평점을 남길 수 없음
        if not room.settlement_result:
            return JsonResponse({
                'ok': True,
                'can_rate': False,
                'reason': 'NO_SETTLEMENT',
                'participants': []
            })
        
        # 자신을 제외한 모든 참여자 목록 가져오기
        participants = RoomParticipant.objects.filter(room=room).exclude(user=request.user).select_related('user')
        participants_data = []
        
        for participant in participants:
            user = participant.user
            # 이미 해당 참여자에게 평점을 남겼는지 확인
            has_rated = RoomRating.objects.filter(room=room, rater=request.user, host=user).exists()
            
            participants_data.append({
                'id': user.id,
                'name': user.name,
                'username': user.username,
                'is_host': room.created_by == user,
                'has_rated': has_rated,
                'trust_score': user.trust_score
            })
        
        return JsonResponse({
            'ok': True,
            'can_rate': True,
            'participants': participants_data
        })
        
    except Room.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'NOT_FOUND'}, status=404)
