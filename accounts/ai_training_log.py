from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional

from django.conf import settings
from django.utils import timezone

# Optional deps
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

from .models import Room


FEATURES = [
    'distance_km',
    'time_diff_hours',
    'jaccard_score',
    'current_participants',
    'host_trust_score',
]


def _dataset_path() -> Path:
    base = Path(settings.BASE_DIR)
    return base / 'media' / 'datasets' / 'training_data.csv'


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_training_rows(rows: Iterable[Dict[str, Any]]) -> None:
    """Append rows to training_data.csv using the existing header if present.
    If the file does not exist, create it with the standard header:
    distance_km,time_diff_hours,current_participants,host_trust_score,jaccard_score,user_categories,room_categories,is_clicked
    """
    target = _dataset_path()
    _ensure_parent_dir(target)
    file_exists = target.exists() and target.stat().st_size > 0

    default_fields = [
        'distance_km',
        'time_diff_hours',
        'current_participants',
        'host_trust_score',
        'jaccard_score',
        'user_categories',
        'room_categories',
        'is_clicked',
    ]

    if file_exists:
        # Read header from file to ensure column compatibility
        with target.open('r', encoding='utf-8') as rf:
            reader = csv.reader(rf)
            try:
                existing_header = next(reader)
                fieldnames = [h.strip() for h in existing_header if h]
                if not fieldnames:
                    fieldnames = default_fields
            except StopIteration:
                fieldnames = default_fields
    else:
        fieldnames = default_fields

    with target.open('a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            # Normalize categories as comma-separated strings if lists provided
            rc = row.get('room_categories')
            if isinstance(rc, (list, tuple)):
                row['room_categories'] = ','.join(str(x) for x in rc)
            uc = row.get('user_categories')
            if isinstance(uc, (list, tuple)):
                row['user_categories'] = ','.join(str(x) for x in uc)

            safe_row = {k: row.get(k, '') for k in fieldnames}
            writer.writerow(safe_row)


# ---- Feature builders (duplicated minimal logic to avoid circular import with views) ----

_EPSG_CANDIDATES = [
    'EPSG:5179',
    'EPSG:5181',
    'EPSG:5186',
    'EPSG:2097',
    'EPSG:4326',
]

_TRANSFORMERS = {}
if Transformer:
    for code in list(_EPSG_CANDIDATES):
        try:
            _TRANSFORMERS[code] = Transformer.from_crs(code, 'EPSG:4326', always_xy=True)
        except Exception:
            pass


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
        try:
            d = geodesic(my_pos, (lat, lon)).km
        except Exception:
            d = 1e9
        if (best is None) or (d < best[0]):
            best = (d, pair, code)
    return best[1] if best else None


def build_features_for_room(
    *,
    room: Room,
    user_lat: float,
    user_lng: float,
    desired_time_iso: str,
    user_categories: list,
) -> Optional[Dict[str, Any]]:
    if geodesic is None:
        return None
    my_lat, my_lon = float(user_lat), float(user_lng)
    # distance
    pair = _tm_to_wgs84_auto(room.x, room.y, my_lat, my_lon)
    if not pair and room.x is not None and room.y is not None:
        try:
            if _in_korea(float(room.y), float(room.x)):
                pair = (float(room.y), float(room.x))
        except Exception:
            pair = None
    if not pair:
        return None
    room_lat, room_lon = pair
    distance_km = geodesic((my_lat, my_lon), (room_lat, room_lon)).km

    # time diff
    if isoparse:
        try:
            desired_dt = isoparse(desired_time_iso)
            meetup = room.meetup_at
            if meetup.tzinfo is None and desired_dt.tzinfo is not None:
                desired_dt = desired_dt.replace(tzinfo=None)
            elif meetup.tzinfo is not None and desired_dt.tzinfo is None:
                meetup = meetup.replace(tzinfo=None)
            diff_hours = abs((meetup - desired_dt).total_seconds()) / 3600.0
        except Exception:
            diff_hours = 24.0
    else:
        diff_hours = 24.0

    # jaccard
    try:
        if isinstance(room.categories, str):
            set_room = set(c.strip() for c in room.categories.split(',') if c.strip())
        else:
            set_room = set(str(x) for x in (room.categories or []))
        set_user = set(str(x) for x in (user_categories or []))
        inter = len(set_room.intersection(set_user))
        uni = len(set_room.union(set_user))
        jaccard = round(inter / uni, 3) if uni else 0.0
    except Exception:
        jaccard = 0.0

    # other features
    try:
        current = int(room.current_participants_cached)
    except Exception:
        current = room.participants.count()
    try:
        trust = float(room.host_trust_score or 0.0)
    except Exception:
        trust = 0.0

    return {
        'distance_km': round(float(distance_km), 6),
        'time_diff_hours': round(float(diff_hours), 2),
        'jaccard_score': float(jaccard),
        'current_participants': int(current),
        'host_trust_score': round(float(trust), 1),
    }


