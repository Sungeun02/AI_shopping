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

# gunicorn 명시적 설치 (requirements.txt에 있지만 확실히 설치)
RUN pip install --no-cache-dir gunicorn

# gunicorn 설치 확인
RUN python -c "import gunicorn; print('gunicorn version:', gunicorn.__version__)"

# Copy the rest of the application code
COPY . .

# 시작 스크립트 복사 및 실행 권한 부여
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Expose port
EXPOSE 8000

# 시작 스크립트 실행
# 마이그레이션과 collectstatic을 자동으로 실행한 후 Gunicorn 시작
CMD ["/app/start.sh"]
