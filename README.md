# AI Shopping - Django 로그인 시스템

Django를 사용한 AI 쇼핑 플랫폼의 로그인 시스템입니다.

## 기능

- ✅ 사용자 회원가입
- ✅ 사용자 로그인/로그아웃
- ✅ 대시보드
- ✅ 반응형 웹 디자인
- ✅ Bootstrap 5 UI
- ✅ 커스텀 User 모델

## 설치 및 실행

### 1. 가상환경 생성 및 활성화

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 데이터베이스 마이그레이션

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. 슈퍼유저 생성 (선택사항)

```bash
python manage.py createsuperuser
```

### 5. 개발 서버 실행

```bash
python manage.py runserver
```

브라우저에서 `http://127.0.0.1:8000/`으로 접속하세요.

## 프로젝트 구조

```
ai_shopping/
├── ai_shopping/          # Django 프로젝트 설정
│   ├── __init__.py
│   ├── settings.py      # 프로젝트 설정
│   ├── urls.py          # 메인 URL 설정
│   ├── wsgi.py
│   └── asgi.py
├── accounts/            # 사용자 인증 앱
│   ├── __init__.py
│   ├── admin.py         # 관리자 설정
│   ├── apps.py
│   ├── forms.py         # 사용자 폼
│   ├── models.py        # User 모델
│   ├── urls.py          # 앱 URL 설정
│   └── views.py         # 뷰 함수
├── templates/           # HTML 템플릿
│   ├── base.html        # 기본 템플릿
│   └── accounts/        # 인증 관련 템플릿
│       ├── login.html
│       ├── signup.html
│       └── dashboard.html
├── static/              # 정적 파일
│   └── css/
│       └── style.css
├── manage.py
├── requirements.txt
└── README.md
```

## 주요 기능 설명

### 1. 사용자 인증
- 커스텀 User 모델 사용
- 이메일, 전화번호 등 추가 필드 지원
- Django의 기본 인증 시스템 활용

### 2. 로그인 시스템
- 사용자명/비밀번호 로그인
- 로그인 후 대시보드로 리다이렉트
- 로그아웃 기능

### 3. 회원가입
- 사용자명, 이메일, 전화번호, 비밀번호 입력
- 폼 유효성 검사
- 회원가입 후 로그인 페이지로 리다이렉트

### 4. 대시보드
- 사용자 정보 표시
- 시스템 상태 확인
- 향후 AI 쇼핑 기능을 위한 준비

## 기술 스택

- **Backend**: Django 4.2.7
- **Frontend**: Bootstrap 5, Font Awesome
- **Database**: SQLite (개발용)
- **Language**: Python 3.x

## 다음 단계

1. AI 쇼핑 추천 시스템 구현
2. 상품 데이터베이스 구축
3. 사용자 선호도 분석
4. 개인화된 쇼핑 경험 제공

## 라이선스

MIT License
