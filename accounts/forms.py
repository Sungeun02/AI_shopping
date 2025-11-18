from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django import forms

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """커스텀 사용자 생성 폼"""
    name = forms.CharField(max_length=150, required=True, label='이름')
    age = forms.IntegerField(required=False, label='나이', min_value=0)
    gender = forms.ChoiceField(required=False, label='성별', choices=(('M', '남성'), ('F', '여성'), ('U', '기타/미상')))
    phone = forms.CharField(max_length=20, required=False, label='전화번호')
    
    class Meta:
        model = User
        fields = ('username', 'name', 'age', 'gender', 'phone', 'password1', 'password2')
        labels = {
            'username': '아이디',
            'password1': '비밀번호',
            'password2': '비밀번호 확인',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 필드에 CSS 클래스 추가
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.name = self.cleaned_data.get('name')
        user.age = self.cleaned_data.get('age')
        user.gender = self.cleaned_data.get('gender')
        user.phone = self.cleaned_data.get('phone')
        user.trust_score = 3.0  # 회원가입 시 신뢰도 3.0으로 시작
        if commit:
            user.save()
        return user


class UserProfileUpdateForm(forms.ModelForm):
    """회원정보 수정 폼 (아이디와 비밀번호는 수정 불가)"""
    class Meta:
        model = User
        fields = ('name', 'age', 'gender', 'phone')
        labels = {
            'name': '이름',
            'age': '나이',
            'gender': '성별',
            'phone': '전화번호',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # gender 필드에 빈 선택지 추가
        self.fields['gender'].choices = [('', '선택하세요')] + list(User.GENDER_CHOICES)
