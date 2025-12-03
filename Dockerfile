# Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (PostgreSQL용)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Collect static files는 배포 후 수동 실행
# (빌드 단계에서는 제외하여 오류 방지)
# 배포 후 Shell에서: python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Run Gunicorn (프로덕션 서버)
# Render는 $PORT 환경변수를 제공하므로 이를 사용 (기본값 8000)
# 에러 발생 시 메시지 출력을 위해 shell 형식 사용
CMD ["sh", "-c", "exec gunicorn ai_shopping.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
