from __future__ import annotations

import os
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_SCHED = None


def _job_auto_close_rooms():
    """약속 시간 10분 전인 방을 자동으로 모집완료로 변경"""
    try:
        from accounts.models import Room
        now = timezone.now()
        cutoff_time = now + timedelta(minutes=10)
        
        # 모집중 상태이고 약속 시간이 10분 이내인 방들을 찾아서 모집완료로 변경
        rooms_to_close = Room.objects.filter(
            status=Room.STATUS_RECRUITING,
            meetup_at__lte=cutoff_time,
            meetup_at__gt=now
        )
        count = 0
        for room in rooms_to_close:
            room.update_status()
            if room.status == Room.STATUS_FULL:
                count += 1
        
        if count > 0:
            logger.info(f"Auto-closed {count} room(s) at {now.isoformat()}")
    except Exception as e:
        logger.error(f"Auto-close rooms job failed: {e}")


def start_scheduler():
    global _SCHED
    if _SCHED is not None:
        return _SCHED
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception as e:
        logger.warning("APScheduler not available: %s", e)
        return None

    # Avoid double start in autoreload
    if os.environ.get('RUN_MAIN') == 'true' or not settings.DEBUG:
        from apscheduler.triggers.interval import IntervalTrigger
        sched = BackgroundScheduler(timezone=str(settings.TIME_ZONE))
        sched.add_job(
            _job_auto_close_rooms,
            IntervalTrigger(minutes=1),  # every 1 minute
            id='auto_close_rooms',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        sched.start()
        _SCHED = sched
        logger.info("APScheduler started: auto_close_rooms every 1 minute")
        return sched
    return None




