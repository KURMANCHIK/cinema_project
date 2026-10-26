from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, BooleanField, Count, Exists, OuterRef, Q, Value
from django.urls import reverse
from django.utils import timezone

MIN_RELEASE_YEAR = 1895
MAX_RELEASE_YEAR = 2100
NEW_RELEASE_DAYS = 30
REVIEW_EDIT_HOURS = 24


class Category(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    description = models.TextField("Описание", blank=True)
    created_at = models.DateTimeField("Создан", default=timezone.now, editable=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "Жанр"
        verbose_name_plural = "Жанры"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"{reverse('catalog')}?genre={self.pk}"


class Country(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    code = models.CharField("Код ISO", max_length=2, unique=True, help_text="Две латинские буквы, например RU")

    class Meta:
        ordering = ["name"]
        verbose_name = "Страна"
        verbose_name_plural = "Страны"

    def __str__(self):
        return self.name


class SubscriptionPlan(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    price = models.DecimalField("Цена, ₽", max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    duration_days = models.PositiveIntegerField("Срок действия, дней", validators=[MinValueValidator(1)])
    description = models.TextField("Описание", blank=True)
    is_active = models.BooleanField("Доступен для покупки", default=True)

    class Meta:
        ordering = ["price"]
        verbose_name = "Тариф подписки"
        verbose_name_plural = "Тарифы подписки"

    def __str__(self):
        return f"{self.name} ({self.price:.0f} ₽ / {self.duration_days} дн.)"

    def price_per_day(self):
        return round(self.price / self.duration_days, 2)


class Person(models.Model):
    full_name = models.CharField("Имя и фамилия", max_length=200)
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    photo = models.ImageField("Фото", upload_to="persons/", blank=True, null=True)
    biography = models.TextField("Биография", blank=True)
    wiki_url = models.URLField("Ссылка на Википедию", blank=True)
    created_at = models.DateTimeField("Добавлен", default=timezone.now, editable=False)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Персона"
        verbose_name_plural = "Персоны"

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse("person-page", args=[self.pk])

    def age(self):
        if not self.birth_date:
            return None
        today = timezone.localdate()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years


class MovieQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Movie.Status.PUBLISHED)

    def released(self):
        return self.published().filter(Q(premiere_date__isnull=True) | Q(premiere_date__lte=timezone.localdate()))

    def new_releases(self, days=NEW_RELEASE_DAYS):
        today = timezone.localdate()
        return self.published().filter(premiere_date__gt=today - timedelta(days=days), premiere_date__lte=today)

    def coming_soon(self):
        return self.published().filter(premiere_date__gt=timezone.localdate())

    def free(self):
        return self.released().filter(access=Movie.Access.FREE)

    def with_related(self):
        return self.select_related("category").prefetch_related("countries")

    def with_stats(self, user=None):
        queryset = self.annotate(
            avg_rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
            reviews_count=Count("reviews", filter=Q(reviews__is_approved=True), distinct=True),
        )
        if user is not None and user.is_authenticated:
            favorites = Favorite.objects.filter(user=user, movie=OuterRef("pk"))
            return queryset.annotate(is_favorite=Exists(favorites))
        return queryset.annotate(is_favorite=Value(False, output_field=BooleanField()))

    def search(self, text, match_case=False):
        lookup = "contains" if match_case else "icontains"
        return self.filter(Q(**{f"title__{lookup}": text}) | Q(**{f"description__{lookup}": text}))


class Movie(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"

    class Access(models.TextChoices):
        FREE = "free", "Бесплатно"
        SUBSCRIPTION = "subscription", "По подписке"

    class AgeRating(models.TextChoices):
        ALL = "0+", "0+"
        SIX = "6+", "6+"
        TWELVE = "12+", "12+"
        SIXTEEN = "16+", "16+"
        ADULT = "18+", "18+"

    title = models.CharField("Название", max_length=255)
    original_title = models.CharField("Оригинальное название", max_length=255, blank=True)
    description = models.TextField("Описание")
    release_year = models.IntegerField(
        "Год выпуска",
        validators=[MinValueValidator(MIN_RELEASE_YEAR), MaxValueValidator(MAX_RELEASE_YEAR)],
    )
    premiere_date = models.DateField("Дата премьеры на сайте", null=True, blank=True)
    duration_minutes = models.PositiveIntegerField("Продолжительность (мин)")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movies", verbose_name="Жанр",
    )
    countries = models.ManyToManyField(Country, related_name="movies", blank=True, verbose_name="Страны")
    persons = models.ManyToManyField(
        Person,
        through="MovieCredit",
        through_fields=("movie", "person"),
        related_name="movies",
        blank=True,
        verbose_name="Съёмочная группа",
    )
    age_rating = models.CharField("Возрастной рейтинг", max_length=3, choices=AgeRating.choices, default=AgeRating.TWELVE)
    access = models.CharField("Доступ", max_length=12, choices=Access.choices, default=Access.SUBSCRIPTION)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.PUBLISHED)
    poster = models.ImageField("Постер", upload_to="posters/", blank=True, null=True)
    trailer_url = models.URLField("Ссылка на трейлер", blank=True)
    subtitles = models.FileField(
        "Файл субтитров",
        upload_to="subtitles/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["srt", "vtt"])],
    )
    views_count = models.PositiveIntegerField("Количество просмотров", default=0)
    created_at = models.DateTimeField("Добавлен", default=timezone.now, editable=False)
    updated_at = models.DateTimeField("Изменён", auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_movies", verbose_name="Кто добавил",
    )

    objects = MovieQuerySet.as_manager()

    class Meta:
        ordering = ["-views_count", "title"]
        verbose_name = "Фильм"
        verbose_name_plural = "Фильмы"
        constraints = [
            models.UniqueConstraint(fields=["title", "release_year"], name="unique_movie_title_year")
        ]

    def clean(self):
        if self.release_year is not None and not MIN_RELEASE_YEAR <= self.release_year <= MAX_RELEASE_YEAR:
            raise ValidationError(
                {"release_year": f"Год выпуска должен быть между {MIN_RELEASE_YEAR} и {MAX_RELEASE_YEAR}."}
            )
        if self.premiere_date and self.release_year and self.premiere_date.year < self.release_year:
            raise ValidationError({"premiere_date": "Премьера на сайте не может быть раньше года выпуска."})

    def __str__(self):
        return f"{self.title} ({self.release_year})"

    def get_absolute_url(self):
        return reverse("movie-page", args=[self.pk])

    @property
    def formatted_duration(self):
        hours, minutes = divmod(self.duration_minutes, 60)
        return f"{hours} ч. {minutes} мин."

    def days_since_premiere(self):
        if not self.premiere_date:
            return None
        return (timezone.localdate() - self.premiere_date).days

    @property
    def is_new(self):
        days = self.days_since_premiere()
        return days is not None and 0 <= days < NEW_RELEASE_DAYS

    @property
    def is_coming_soon(self):
        days = self.days_since_premiere()
        return days is not None and days < 0

    def days_until_premiere(self):
        days = self.days_since_premiere()
        return -days if days is not None and days < 0 else 0

    def average_rating(self):
        return self.reviews.filter(is_approved=True).aggregate(value=Avg("rating"))["value"]

    def directors(self):
        return [credit.person for credit in self.credits.all() if credit.role == MovieCredit.Role.DIRECTOR]

    def is_available_for(self, user):
        if self.access == self.Access.FREE or user.is_staff:
            return True
        return user.is_authenticated and Subscription.objects.active().filter(user=user).exists()


class MovieCredit(models.Model):
    class Role(models.TextChoices):
        DIRECTOR = "director", "Режиссёр"
        ACTOR = "actor", "Актёр"
        WRITER = "writer", "Сценарист"
        COMPOSER = "composer", "Композитор"

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="credits", verbose_name="Фильм")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="credits", verbose_name="Персона")
    role = models.CharField("Роль в фильме", max_length=10, choices=Role.choices, default=Role.ACTOR)
    character_name = models.CharField("Имя персонажа", max_length=200, blank=True)
    order = models.PositiveSmallIntegerField("Порядок в титрах", default=1)

    class Meta:
        ordering = ["movie", "order"]
        verbose_name = "Участие в фильме"
        verbose_name_plural = "Участие в фильмах"
        constraints = [
            models.UniqueConstraint(fields=["movie", "person", "role"], name="unique_credit_movie_person_role")
        ]

    def __str__(self):
        return f"{self.person} — {self.get_role_display()} («{self.movie.title}»)"


class ApprovedReviewManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_approved=True)


class Review(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews", verbose_name="Фильм")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews", verbose_name="Автор")
    text = models.TextField("Текст отзыва")
    rating = models.IntegerField("Оценка (1-10)", choices=[(i, i) for i in range(1, 11)])
    is_approved = models.BooleanField("Одобрен модератором", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    objects = models.Manager()
    approved = ApprovedReviewManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        constraints = [
            models.UniqueConstraint(fields=["user", "movie"], name="unique_review_user_movie")
        ]

    def __str__(self):
        return f"Отзыв от {self.user.username} на {self.movie.title}"

    def get_absolute_url(self):
        return f"{self.movie.get_absolute_url()}#review-{self.pk}"

    @property
    def is_editable(self):
        return timezone.now() - self.created_at < timedelta(hours=REVIEW_EDIT_HOURS)


class Playlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="playlists", verbose_name="Владелец")
    name = models.CharField("Название плейлиста", max_length=255)
    description = models.TextField("Описание", blank=True)
    is_public = models.BooleanField("Публичный", default=False)
    movies = models.ManyToManyField(Movie, related_name="playlists", blank=True, verbose_name="Фильмы")
    created_at = models.DateTimeField("Создан", default=timezone.now, editable=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "Плейлист"
        verbose_name_plural = "Плейлисты"

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites", verbose_name="Пользователь")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="favorited_by", verbose_name="Фильм")
    created_at = models.DateTimeField("Добавлено", default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Избранное"
        verbose_name_plural = "Избранное"
        unique_together = ("user", "movie")

    def __str__(self):
        return f"{self.user.username} → {self.movie.title}"


class SubscriptionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(expires_at__gt=timezone.now())

    def expiring(self, days=3):
        now = timezone.now()
        return self.filter(expires_at__gt=now, expires_at__lte=now + timedelta(days=days))


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriptions", verbose_name="Пользователь")
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions", verbose_name="Тариф"
    )
    started_at = models.DateTimeField("Начало действия", default=timezone.now)
    expires_at = models.DateTimeField("Окончание действия", blank=True)
    price_paid = models.DecimalField("Оплачено, ₽", max_digits=8, decimal_places=2, default=0)
    auto_renew = models.BooleanField("Автопродление", default=False)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self):
        return f"{self.user.username}: {self.plan.name} до {timezone.localtime(self.expires_at):%d.%m.%Y}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.started_at + timedelta(days=self.plan.duration_days)
        if not self.price_paid:
            self.price_paid = self.plan.price
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.expires_at > timezone.now()

    def days_left(self):
        if not self.is_active:
            return 0
        return (self.expires_at - timezone.now()).days

    def extend(self, days):
        base = max(self.expires_at, timezone.now())
        self.expires_at = base + timedelta(days=days)
        self.save(update_fields=["expires_at"])
        return self.expires_at
