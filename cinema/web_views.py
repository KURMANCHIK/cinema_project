from datetime import date, timedelta

from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.cache import cache
from django.db.models import Avg, Count, F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import MovieForm, RegisterForm, ReviewForm
from .models import (
    Category, Country, Favorite, Movie, MovieCredit, Person, Review, Subscription, SubscriptionPlan,
)
from .tasks import send_thank_you_email

SORT_OPTIONS = {
    "popular": ["-views_count", "title"],
    "rating": [F("avg_rating").desc(nulls_last=True), "title"],
    "new": [F("premiere_date").desc(nulls_last=True), "title"],
    "year": ["-release_year", "title"],
    "title": ["title"],
}

MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def visible_movies(user):
    queryset = Movie.objects.all() if user.is_staff else Movie.objects.published()
    return queryset.with_related().with_stats(user)


def home_stats():
    totals = Movie.objects.published().aggregate(
        movies=Count("id"), views=Sum("views_count"), avg_duration=Avg("duration_minutes"),
    )
    return {
        "movies": totals["movies"],
        "views": totals["views"] or 0,
        "avg_duration": round(totals["avg_duration"] or 0),
        "persons": Person.objects.count(),
        "reviews": Review.approved.count(),
        "subscribers": Subscription.objects.active().values("user").distinct().count(),
    }


class HomeView(TemplateView):
    template_name = "cinema/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        movies = Movie.objects.published().with_related().with_stats(user)

        context["new_releases"] = movies.new_releases().order_by("-premiere_date")[:4]
        context["popular"] = movies.released().annotate(fans=Count("favorited_by", distinct=True)).order_by("-views_count", "-fans")[:4]
        context["top_rated"] = movies.released().filter(reviews_count__gte=2).order_by(F("avg_rating").desc(nulls_last=True))[:5]
        context["coming_soon"] = movies.coming_soon().order_by("premiere_date")[:5]
        context["month_url"] = reverse("premieres-by-month", args=[today.year, f"{today.month:02d}"])
        context["genres"] = (
            Category.objects.annotate(total=Count("movies", filter=Q(movies__status=Movie.Status.PUBLISHED)))
            .filter(total__gt=0)
            .order_by("-total")
            .values("id", "name", "total")
        )
        context["stars"] = (
            Person.objects.annotate(total=Count("credits", filter=Q(credits__movie__status=Movie.Status.PUBLISHED)))
            .filter(total__gt=0)
            .order_by("-total", "full_name")[:6]
        )
        context["fresh_reviews"] = Review.approved.select_related("movie", "user").prefetch_related("user__socialaccount_set")[:4]
        context["plans"] = SubscriptionPlan.objects.filter(is_active=True)
        context["free_movies"] = movies.free().order_by("-views_count")[:4]
        context["stats"] = cache.get_or_set("home_stats", home_stats, 60)
        if user.is_authenticated:
            context["subscription"] = Subscription.objects.active().filter(user=user).select_related("plan").first()
        return context


class CatalogView(ListView):
    template_name = "cinema/catalog.html"
    context_object_name = "movies"
    paginate_by = 12

    def get_queryset(self):
        params = self.request.GET
        movies = visible_movies(self.request.user)
        self.query = params.get("q", "").strip()
        self.match_case = bool(params.get("match_case"))
        if self.query:
            movies = movies.search(self.query, match_case=self.match_case)
        genre = params.get("genre", "")
        if genre:
            if not genre.isdigit() or not Category.objects.filter(pk=genre).exists():
                raise Http404("Жанр не найден")
            movies = movies.filter(category_id=genre)
        country = params.get("country", "")
        if country:
            movies = movies.filter(countries__code__iexact=country)
        if params.get("free"):
            movies = movies.exclude(access=Movie.Access.SUBSCRIPTION)
        if params.get("no_adult"):
            movies = movies.exclude(age_rating=Movie.AgeRating.ADULT)
        self.sort = params.get("sort", "popular")
        return movies.distinct().order_by(*SORT_OPTIONS.get(self.sort, SORT_OPTIONS["popular"]))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context.update({
            "genres": Category.objects.all(),
            "countries": Country.objects.filter(movies__isnull=False).distinct(),
            "query": self.query,
            "match_case": self.match_case,
            "sort": self.sort,
            "params": self.request.GET,
            "querystring": params.urlencode(),
        })
        return context


def premieres_by_month(request, year, month):
    year, month = int(year), int(month)
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    movies = (
        Movie.objects.published().with_related().with_stats(request.user)
        .filter(premiere_date__gte=start, premiere_date__lt=end)
        .order_by("premiere_date")
    )
    previous = start - timedelta(days=1)
    return render(request, "cinema/premieres.html", {
        "movies": movies,
        "title": f"{MONTHS[month - 1].capitalize()} {year}",
        "prev_url": reverse("premieres-by-month", args=[previous.year, f"{previous.month:02d}"]),
        "next_url": reverse("premieres-by-month", args=[end.year, f"{end.month:02d}"]),
    })


def movie_detail(request, pk):
    queryset = visible_movies(request.user).prefetch_related("credits__person")
    try:
        movie = queryset.get(pk=pk)
    except Movie.DoesNotExist:
        messages.warning(request, "Такого фильма нет или он был удалён.")
        return redirect("catalog")

    if request.method == "GET":
        Movie.objects.filter(pk=pk).update(views_count=F("views_count") + 1)
        movie.views_count += 1

    reviews = Review.approved.filter(movie=movie).select_related("user").prefetch_related("user__socialaccount_set")
    credits = list(movie.credits.all())
    user_review = None
    form = None

    if request.user.is_authenticated:
        user_review = Review.objects.filter(movie=movie, user=request.user).first()
        if user_review is None:
            form = ReviewForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                review = form.save(commit=False)
                review.movie = movie
                review.user = request.user
                review.save()
                if request.user.email:
                    send_thank_you_email.delay(request.user.email, movie.title)
                messages.success(request, "Спасибо! Отзыв опубликован.")
                return redirect(movie.get_absolute_url())

    similar = (
        Movie.objects.published().filter(category=movie.category).exclude(pk=movie.pk)
        .with_stats(request.user).order_by("-views_count")[:4]
    )
    return render(request, "cinema/detail.html", {
        "movie": movie,
        "directors": [c for c in credits if c.role == MovieCredit.Role.DIRECTOR],
        "cast": [c for c in credits if c.role == MovieCredit.Role.ACTOR],
        "crew": [c for c in credits if c.role not in (MovieCredit.Role.DIRECTOR, MovieCredit.Role.ACTOR)],
        "reviews": reviews,
        "form": form,
        "user_review": user_review,
        "similar": similar,
        "can_watch": movie.is_available_for(request.user),
        "page_url": request.build_absolute_uri(),
        "printed_at": timezone.localtime(),
    })


def person_detail(request, pk):
    person = get_object_or_404(Person, pk=pk)
    credits = (
        person.credits.filter(movie__status=Movie.Status.PUBLISHED)
        .select_related("movie", "movie__category")
        .order_by("-movie__release_year")
    )
    return render(request, "cinema/person.html", {"person": person, "credits": credits})


@login_required
@require_POST
def toggle_favorite(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, movie=movie)
    if not created:
        favorite.delete()
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(movie.get_absolute_url())


@login_required
def favorites(request):
    movies = Movie.objects.published().with_related().with_stats(request.user).filter(favorited_by__user=request.user)
    return render(request, "cinema/favorites.html", {"movies": movies})


class ReviewAuthorMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        review = self.get_object()
        user = self.request.user
        return user.is_staff or (review.user_id == user.id and review.is_editable)


class ReviewUpdateView(ReviewAuthorMixin, UpdateView):
    model = Review
    form_class = ReviewForm
    template_name = "cinema/review_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Отзыв обновлён.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.movie.get_absolute_url()


class ReviewDeleteView(ReviewAuthorMixin, DeleteView):
    model = Review
    template_name = "cinema/review_confirm_delete.html"

    def get_success_url(self):
        return self.object.movie.get_absolute_url()

    def form_valid(self, form):
        messages.success(self.request, "Отзыв удалён.")
        return super().form_valid(form)


class StaffRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class ManageMoviesView(StaffRequiredMixin, ListView):
    template_name = "cinema/manage.html"
    context_object_name = "movies"
    paginate_by = 20

    def get_queryset(self):
        return (
            Movie.objects.select_related("category")
            .annotate(reviews_total=Count("reviews", distinct=True))
            .order_by("-created_at")
        )


class MovieCreateView(StaffRequiredMixin, CreateView):
    model = Movie
    form_class = MovieForm
    template_name = "cinema/movie_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Фильм «{self.object.title}» добавлен.")
        return response


class MovieUpdateView(StaffRequiredMixin, UpdateView):
    model = Movie
    form_class = MovieForm
    template_name = "cinema/movie_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Изменения в «{self.object.title}» сохранены.")
        return response


class MovieDeleteView(StaffRequiredMixin, DeleteView):
    model = Movie
    template_name = "cinema/movie_confirm_delete.html"
    success_url = reverse_lazy("manage-movies")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reviews_total"] = self.object.reviews.count()
        context["credits_total"] = self.object.credits.count()
        return context

    def form_valid(self, form):
        title = self.object.title
        response = super().form_valid(form)
        messages.success(self.request, f"Фильм «{title}» удалён.")
        return response


@login_required
@require_POST
def subscribe(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, pk=plan_id, is_active=True)
    current = Subscription.objects.active().filter(user=request.user).order_by("-expires_at").first()
    if current:
        current.extend(plan.duration_days)
        messages.success(request, f"Подписка продлена до {timezone.localtime(current.expires_at):%d.%m.%Y}.")
    else:
        subscription = Subscription.objects.create(user=request.user, plan=plan)
        messages.success(request, f"Подписка «{plan.name}» активна до {timezone.localtime(subscription.expires_at):%d.%m.%Y}.")
    return redirect("profile")


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Добро пожаловать, {user.username}!")
        return redirect("home")
    return render(request, "cinema/register.html", {"form": form})


@login_required
def profile(request):
    user = request.user
    google_account = SocialAccount.objects.filter(user=user, provider="google").first()
    google_data = google_account.extra_data if google_account else {}
    return render(request, "cinema/profile.html", {
        "google_account": google_account,
        "google_name": google_data.get("name", ""),
        "google_email": google_data.get("email", ""),
        "can_disconnect": user.has_usable_password(),
        "reviews": user.reviews.select_related("movie")[:10],
        "reviews_count": user.reviews.count(),
        "favorites_count": user.favorites.count(),
        "playlists": user.playlists.annotate(total=Count("movies")),
        "subscription": user.subscriptions.active().select_related("plan").order_by("-expires_at").first(),
        "history": user.subscriptions.select_related("plan")[:5],
        "plans": SubscriptionPlan.objects.filter(is_active=True),
    })


@login_required
@require_POST
def google_disconnect(request):
    if not request.user.has_usable_password():
        messages.error(request, "Сначала задайте пароль. Иначе вы не сможете войти после отвязки Google.")
        return redirect("profile")
    deleted, _ = SocialAccount.objects.filter(user=request.user, provider="google").delete()
    if deleted:
        messages.success(request, "Google-аккаунт отвязан.")
    return redirect("profile")
