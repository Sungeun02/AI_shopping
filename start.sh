#!/bin/bash
# Render 배포 시 자동 실행 스크립트

# 마이그레이션이 필요한지 확인하고 실행
python manage.py migrate --noinput

# 정적 파일 수집
python manage.py collectstatic --noinput

# Gunicorn 시작
exec python -m gunicorn ai_shopping.wsgi:application --bind 0.0.0.0:${PORT:-8000}

