from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Category, Country, Movie, Review
from .serializers import contains_forbidden_words


class BootstrapMixin:
    def setup_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class ReviewForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 4, "placeholder": "Ваши впечатления о фильме"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_bootstrap()

    def clean_text(self):
        text = self.cleaned_data["text"]
        if contains_forbidden_words(text):
            raise forms.ValidationError("Комментарий содержит запрещенные слова!")
        return text


class MovieForm(BootstrapMixin, forms.ModelForm):
    countries = forms.ModelMultipleChoiceField(
        queryset=Country.objects.all(), required=False, label="Страны",
        help_text="Несколько стран — с зажатой клавишей Ctrl",
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )

    class Meta:
        model = Movie
        fields = [
            "title", "original_title", "description", "category", "countries", "release_year", "premiere_date",
            "duration_minutes", "age_rating", "access", "status", "poster", "trailer_url", "subtitles",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "premiere_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {
            "poster": "JPG или PNG, до 5 МБ",
            "subtitles": "Файл .srt или .vtt",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()
        self.fields["category"].empty_label = "— без жанра —"
        for name in ("original_title", "premiere_date", "poster", "trailer_url", "subtitles", "category"):
            self.fields[name].required = False
        self.setup_bootstrap()

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Название не может быть пустым.")
        return title

    def clean_poster(self):
        poster = self.cleaned_data.get("poster")
        if poster and hasattr(poster, "size") and poster.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Постер больше 5 МБ.")
        return poster


class RegisterForm(BootstrapMixin, UserCreationForm):
    email = forms.EmailField(required=True, label="Email")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_bootstrap()

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return email


class LoginForm(BootstrapMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_bootstrap()
