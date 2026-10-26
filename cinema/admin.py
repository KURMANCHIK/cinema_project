from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Avg, Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from . import pdf
from .models import (
    Category, Country, Favorite, Movie, MovieCredit, Person, Playlist, Review, Subscription, SubscriptionPlan,
)

admin.site.site_header = "Cinema — администрирование"
admin.site.site_title = "Cinema"
admin.site.index_title = "Управление онлайн-кинотеатром"


def admin_link(model, pk, text):
    if pk is None:
        return "—"
    url = reverse(f"admin:cinema_{model}_change", args=[pk])
    return format_html('<a href="{}">{}</a>', url, text)


def pdf_response(content, filename, inline=False):
    response = HttpResponse(content, content_type="application/pdf")
    mode = "inline" if inline else "attachment"
    response["Content-Disposition"] = f'{mode}; filename="{filename}"'
    return response


class MovieCreditInline(admin.TabularInline):
    model = MovieCredit
    extra = 1
    raw_id_fields = ("person",)
    fields = ("person", "role", "character_name", "order")


class PersonCreditInline(admin.TabularInline):
    model = MovieCredit
    extra = 0
    raw_id_fields = ("movie",)
    fields = ("movie", "role", "character_name", "order")
    verbose_name_plural = "Фильмография"


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "rating", "text", "is_approved", "created_at")
    readonly_fields = ("created_at",)


class CategoryMovieInline(admin.TabularInline):
    model = Movie
    extra = 0
    fields = ("title", "release_year", "status", "views_count")
    readonly_fields = ("title", "release_year", "status", "views_count")
    show_change_link = True
    can_delete = False
    verbose_name_plural = "Фильмы жанра"

    def has_add_permission(self, request, obj=None):
        return False


class CountryMovieInline(admin.TabularInline):
    model = Movie.countries.through
    extra = 0
    raw_id_fields = ("movie",)
    verbose_name = "Фильм страны"
    verbose_name_plural = "Фильмы страны"


class PlanSubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "started_at", "expires_at", "price_paid", "auto_renew")
    readonly_fields = ("price_paid",)
    show_change_link = True


class UserSubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0
    fields = ("plan", "started_at", "expires_at", "price_paid")
    readonly_fields = ("price_paid",)


class UserFavoriteInline(admin.TabularInline):
    model = Favorite
    extra = 0
    raw_id_fields = ("movie",)
    readonly_fields = ("created_at",)


class PlaylistMovieInline(admin.TabularInline):
    model = Playlist.movies.through
    extra = 0
    raw_id_fields = ("movie",)
    verbose_name = "Фильм плейлиста"
    verbose_name_plural = "Фильмы плейлиста"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "movies_total", "created_at")
    list_display_links = ("name",)
    list_filter = ("created_at",)
    search_fields = ("name", "description", "movies__title")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    inlines = [CategoryMovieInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_movies=Count("movies"))

    @admin.display(description="Фильмов", ordering="_movies")
    def movies_total(self, obj):
        return obj._movies


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "movies_total")
    list_display_links = ("name",)
    list_filter = ("movies__category",)
    search_fields = ("name", "code", "movies__title")
    inlines = [CountryMovieInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_movies=Count("movies", distinct=True))

    def movies_total(self, obj):
        return obj._movies

    movies_total.short_description = "Фильмов"
    movies_total.admin_order_field = "_movies"


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "duration_days", "price_per_day_column", "active_subscribers", "is_active")
    list_display_links = ("name",)
    list_editable = ("is_active",)
    list_filter = ("is_active", "duration_days")
    search_fields = ("name", "description", "subscriptions__user__username")
    inlines = [PlanSubscriptionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _active=Count("subscriptions", filter=Q(subscriptions__expires_at__gt=timezone.now()))
        )

    @admin.display(description="Цена за день, ₽")
    def price_per_day_column(self, obj):
        return obj.price_per_day()

    @admin.display(description="Активных подписок", ordering="_active")
    def active_subscribers(self, obj):
        return obj._active


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("photo_preview", "full_name", "birth_date", "age_column", "movies_total", "wiki_link")
    list_display_links = ("photo_preview", "full_name")
    list_filter = ("credits__role", "birth_date")
    search_fields = ("full_name", "biography", "movies__title")
    date_hierarchy = "created_at"
    readonly_fields = ("photo_preview", "created_at")
    fields = ("full_name", "birth_date", "photo", "photo_preview", "biography", "wiki_url", "created_at")
    inlines = [PersonCreditInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_movies=Count("movies", distinct=True))

    @admin.display(description="Фото")
    def photo_preview(self, obj):
        if not obj.photo:
            return "—"
        return format_html('<img src="{}" alt="" style="height:48px;border-radius:6px">', obj.photo.url)

    @admin.display(description="Возраст")
    def age_column(self, obj):
        return obj.age() or "—"

    @admin.display(description="Фильмов", ordering="_movies")
    def movies_total(self, obj):
        return obj._movies

    @admin.display(description="Википедия")
    def wiki_link(self, obj):
        if not obj.wiki_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть</a>', obj.wiki_url)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = (
        "poster_preview", "title", "release_year", "category_link", "status", "access",
        "avg_rating", "reviews_total", "views_count", "premiere_label", "pdf_link",
    )
    list_display_links = ("poster_preview", "title")
    list_editable = ("status",)
    list_filter = ("status", "access", "age_rating", ("category", admin.RelatedOnlyFieldListFilter), "countries", "release_year")
    search_fields = ("title", "original_title", "description", "category__name", "persons__full_name", "countries__name")
    date_hierarchy = "created_at"
    raw_id_fields = ("created_by",)
    filter_horizontal = ("countries",)
    readonly_fields = ("poster_preview", "views_count", "created_at", "updated_at", "created_by")
    list_select_related = ("category",)
    inlines = [MovieCreditInline, ReviewInline]
    actions = ["publish", "unpublish", "make_free", "download_pdf"]
    fieldsets = (
        ("Основное", {"fields": ("title", "original_title", "description", "category", "countries")}),
        ("Параметры", {"fields": ("release_year", "premiere_date", "duration_minutes", "age_rating", "access", "status")}),
        ("Медиа", {"fields": ("poster", "poster_preview", "trailer_url", "subtitles")}),
        ("Служебное", {"classes": ("collapse",), "fields": ("views_count", "created_at", "updated_at", "created_by")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
            _reviews=Count("reviews", distinct=True),
        )

    def get_urls(self):
        custom = [path("<int:pk>/pdf/", self.admin_site.admin_view(self.movie_pdf), name="cinema_movie_pdf")]
        return custom + super().get_urls()

    def movie_pdf(self, request, pk):
        movie = get_object_or_404(Movie.objects.with_related(), pk=pk)
        return pdf_response(pdf.movie_card_pdf([movie]), f"movie_{movie.pk}.pdf", inline=True)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Постер")
    def poster_preview(self, obj):
        if not obj.poster:
            return "—"
        return format_html('<img src="{}" alt="" style="height:60px;border-radius:4px">', obj.poster.url)

    @admin.display(description="Жанр", ordering="category__name")
    def category_link(self, obj):
        return admin_link("category", obj.category_id, obj.category.name if obj.category else "—")

    @admin.display(description="Рейтинг", ordering="_rating")
    def avg_rating(self, obj):
        return round(obj._rating, 1) if obj._rating is not None else "—"

    def reviews_total(self, obj):
        return obj._reviews

    reviews_total.short_description = "Отзывов"
    reviews_total.admin_order_field = "_reviews"

    @admin.display(description="Премьера", ordering="premiere_date")
    def premiere_label(self, obj):
        if obj.is_coming_soon:
            return format_html('<span style="color:#b45309">через {} дн.</span>', obj.days_until_premiere())
        if obj.is_new:
            return mark_safe('<b style="color:#15803d">новинка</b>')
        return obj.premiere_date.strftime("%d.%m.%Y") if obj.premiere_date else "—"

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        url = reverse("admin:cinema_movie_pdf", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">карточка</a>', url)

    @admin.action(description="Опубликовать выбранные фильмы")
    def publish(self, request, queryset):
        updated = queryset.update(status=Movie.Status.PUBLISHED)
        self.message_user(request, f"Опубликовано фильмов: {updated}", messages.SUCCESS)

    @admin.action(description="Снять с публикации (в черновики)")
    def unpublish(self, request, queryset):
        updated = queryset.update(status=Movie.Status.DRAFT)
        self.message_user(request, f"Снято с публикации: {updated}", messages.WARNING)

    @admin.action(description="Открыть бесплатный доступ")
    def make_free(self, request, queryset):
        updated = queryset.update(access=Movie.Access.FREE)
        self.message_user(request, f"Бесплатными стали фильмов: {updated}", messages.SUCCESS)

    @admin.action(description="Скачать карточки фильмов (PDF)")
    def download_pdf(self, request, queryset):
        movies = queryset.select_related("category").prefetch_related("countries", "credits__person")
        return pdf_response(pdf.movie_card_pdf(movies), "movies.pdf")


@admin.register(MovieCredit)
class MovieCreditAdmin(admin.ModelAdmin):
    list_display = ("person", "role", "movie_link", "character_name", "order")
    list_display_links = ("person",)
    list_filter = ("role", "movie__category")
    search_fields = ("person__full_name", "movie__title", "character_name")
    raw_id_fields = ("movie", "person")
    list_select_related = ("movie", "person")

    @admin.display(description="Фильм", ordering="movie__title")
    def movie_link(self, obj):
        return admin_link("movie", obj.movie_id, obj.movie.title)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("short_text", "movie_link", "user", "rating", "is_approved", "created_at")
    list_display_links = ("short_text",)
    list_editable = ("is_approved",)
    list_filter = ("is_approved", "rating", "created_at", "movie__category")
    search_fields = ("text", "movie__title", "user__username", "user__email")
    date_hierarchy = "created_at"
    raw_id_fields = ("movie", "user")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("movie", "user")
    actions = ["approve", "hide"]

    @admin.display(description="Отзыв")
    def short_text(self, obj):
        return obj.text if len(obj.text) <= 50 else f"{obj.text[:50]}…"

    @admin.display(description="Фильм", ordering="movie__title")
    def movie_link(self, obj):
        return admin_link("movie", obj.movie_id, obj.movie.title)

    @admin.action(description="Одобрить отзывы")
    def approve(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"Одобрено отзывов: {updated}", messages.SUCCESS)

    @admin.action(description="Скрыть отзывы")
    def hide(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"Скрыто отзывов: {updated}", messages.WARNING)


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "is_public", "movies_total", "created_at")
    list_display_links = ("name",)
    list_filter = ("is_public", "created_at")
    search_fields = ("name", "description", "user__username", "movies__title")
    date_hierarchy = "created_at"
    raw_id_fields = ("user",)
    filter_horizontal = ("movies",)
    readonly_fields = ("created_at",)
    inlines = [PlaylistMovieInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_movies=Count("movies"))

    @admin.display(description="Фильмов", ordering="_movies")
    def movies_total(self, obj):
        return obj._movies


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "movie_link", "created_at")
    list_display_links = ("user",)
    list_filter = ("created_at", "movie__category")
    search_fields = ("user__username", "movie__title")
    date_hierarchy = "created_at"
    raw_id_fields = ("user", "movie")
    readonly_fields = ("created_at",)
    list_select_related = ("user", "movie")

    @admin.display(description="Фильм", ordering="movie__title")
    def movie_link(self, obj):
        return admin_link("movie", obj.movie_id, obj.movie.title)


class ActiveSubscriptionFilter(admin.SimpleListFilter):
    title = "состояние"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return (("active", "Активные"), ("expiring", "Истекают за 3 дня"), ("expired", "Истёкшие"))

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.active()
        if self.value() == "expiring":
            return queryset.expiring()
        if self.value() == "expired":
            return queryset.filter(expires_at__lte=timezone.now())
        return queryset


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "started_at", "expires_at", "state_label", "days_left_column", "price_paid", "receipt_link")
    list_display_links = ("user",)
    list_filter = (ActiveSubscriptionFilter, "plan", "auto_renew", "started_at")
    search_fields = ("user__username", "user__email", "plan__name")
    date_hierarchy = "started_at"
    raw_id_fields = ("user",)
    readonly_fields = ("price_paid",)
    list_select_related = ("user", "plan")
    actions = ["extend_30_days", "download_receipts"]

    def get_urls(self):
        custom = [path("<int:pk>/receipt/", self.admin_site.admin_view(self.receipt), name="cinema_subscription_receipt")]
        return custom + super().get_urls()

    def receipt(self, request, pk):
        subscription = get_object_or_404(Subscription.objects.select_related("user", "plan"), pk=pk)
        return pdf_response(pdf.subscription_receipt_pdf(subscription), f"receipt_{pk}.pdf", inline=True)

    @admin.display(description="Состояние", boolean=True)
    def state_label(self, obj):
        return obj.is_active

    @admin.display(description="Осталось дней")
    def days_left_column(self, obj):
        return obj.days_left()

    @admin.display(description="Квитанция")
    def receipt_link(self, obj):
        url = reverse("admin:cinema_subscription_receipt", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">PDF</a>', url)

    @admin.action(description="Продлить на 30 дней")
    def extend_30_days(self, request, queryset):
        updated = queryset.update(expires_at=F("expires_at") + timedelta(days=30))
        self.message_user(request, f"Продлено подписок: {updated}", messages.SUCCESS)

    @admin.action(description="Скачать квитанцию (PDF)")
    def download_receipts(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Выберите ровно одну подписку.", messages.WARNING)
            return None
        subscription = queryset.select_related("user", "plan").first()
        return pdf_response(pdf.subscription_receipt_pdf(subscription), f"receipt_{subscription.pk}.pdf")


admin.site.unregister(User)


@admin.register(User)
class CinemaUserAdmin(UserAdmin):
    list_display = ("username", "email", "full_name", "is_staff", "reviews_total", "has_subscription", "date_joined")
    list_display_links = ("username",)
    list_filter = UserAdmin.list_filter + ("date_joined",)
    search_fields = UserAdmin.search_fields + ("reviews__movie__title",)
    date_hierarchy = "date_joined"
    readonly_fields = ("last_login", "date_joined")
    inlines = [UserSubscriptionInline, UserFavoriteInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _reviews=Count("reviews", distinct=True),
            _active=Count("subscriptions", filter=Q(subscriptions__expires_at__gt=timezone.now()), distinct=True),
        )

    @admin.display(description="Имя")
    def full_name(self, obj):
        return obj.get_full_name() or "—"

    @admin.display(description="Отзывов", ordering="_reviews")
    def reviews_total(self, obj):
        return obj._reviews

    @admin.display(description="Подписка", boolean=True, ordering="_active")
    def has_subscription(self, obj):
        return obj._active > 0
