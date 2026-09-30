"""Auth & user-management forms — server-side validation + password policy."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import Role

User = get_user_model()

_HELP = "8+ أحرف على الأقل — تُفحص بسياسات كلمات المرور القياسية (Django validators)."


class LoginForm(forms.Form):
    username = forms.CharField(
        label="اسم المستخدم",
        max_length=150,
        widget=forms.TextInput(attrs={"autofocus": True, "class": "form-control"}),
    )
    password = forms.CharField(
        label="كلمة المرور",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="كلمة المرور", strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        help_text=_HELP,
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور", strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    roles = forms.ModelMultipleChoiceField(
        label="الأدوار",
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="اختر دورًا واحدًا على الأقل.",
    )

    class Meta:
        model = User
        fields = ("username", "full_name", "job_title", "is_demo")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "job_title": forms.TextInput(attrs={"class": "form-control"}),
            "is_demo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("اسم المستخدم موجود مسبقًا.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "كلمتا المرور غير متطابقتين.")
            else:
                validate_password(p1)  # security policy enforced server-side
        return cleaned


class UserEditForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        label="الأدوار",
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    class Meta:
        model = User
        fields = ("full_name", "job_title", "is_active", "is_demo")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "job_title": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_demo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["roles"].initial = self.instance.role_links.values_list(
                "role_id", flat=True
            )
