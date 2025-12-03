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

# Collect static files (DB 없이 실행되도록 더미 환경변수 설정)
# collectstatic은 선택적 (실패해도 빌드 계속)
RUN set -e; \
    DATABASE_URL=postgres://dummy:dummy@dummy:5432/dummy \
    SECRET_KEY=dummy-secret-key-for-build \
    DEBUG=False \
    python manage.py collectstatic --noinput || echo "collectstatic failed, continuing..."

# Expose port
EXPOSE 8000

# Run Gunicorn (프로덕션 서버)
CMD ["gunicorn", "ai_shopping.wsgi:application", "--bind", "0.0.0.0:8000"]
