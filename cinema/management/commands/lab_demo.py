import logging
import time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cinema.models import Category, Favorite, Movie, MovieCredit, Person, Review, Subscription, SubscriptionPlan

CYAN, GREEN, YELLOW, GREY, RESET = "\033[1;36m", "\033[32m", "\033[33m", "\033[90m", "\033[0m"


class Command(BaseCommand):
    help = "Демонстрация заданий лабораторных работ №3–6 на данных проекта"

    def add_arguments(self, parser):
        parser.add_argument("--part", type=int, choices=[1, 2, 3, 4], required=True)
        parser.add_argument("--item", help="Номер пункта, например 1.3")

    def handle(self, *args, **options):
        items = {
            1: ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"],
            2: ["2.3", "2.4"],
            3: ["3.1", "3.2", "3.5"],
            4: ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6"],
        }[options["part"]]
        if options["item"]:
            items = [options["item"]]
        for item in items:
            getattr(self, "item_" + item.replace(".", "_"))()

    def title(self, text):
        self.stdout.write(f"\n{CYAN}=== {text} ==={RESET}")

    def line(self, text=""):
        self.stdout.write(text)

    def item_1_1(self):
        self.title("1.1 timezone: работа с датой")
        now = timezone.now()
        self.line(f"timezone.now()       = {now:%Y-%m-%d %H:%M:%S} UTC (так хранится в БД)")
        self.line(f"timezone.localtime() = {timezone.localtime(now):%Y-%m-%d %H:%M:%S} {timezone.get_current_timezone_name()}")
        self.line(f"timezone.localdate() = {timezone.localdate()}")
        movie = Movie.objects.new_releases().order_by("-premiere_date").first()
        soon = Movie.objects.coming_soon().order_by("premiere_date").first()
        self.line(f"Пример 1. Movie.is_new: «{movie.title}» — премьера {movie.premiere_date}, прошло {movie.days_since_premiere()} дн. → is_new={movie.is_new}")
        self.line(f"          «{soon.title}» — премьера {soon.premiere_date} → is_coming_soon={soon.is_coming_soon}, через {soon.days_until_premiere()} дн.")
        sub = Subscription.objects.active().select_related("plan", "user").order_by("expires_at").first()
        self.line(f"Пример 2. Subscription: {sub.user.username}, тариф «{sub.plan.name}», начало {timezone.localtime(sub.started_at):%d.%m.%Y}")
        self.line(f"          expires_at = started_at + {sub.plan.duration_days} дн. = {timezone.localtime(sub.expires_at):%d.%m.%Y %H:%M} → is_active={sub.is_active}, осталось {sub.days_left()} дн.")
        review = Review.objects.order_by("-created_at").first()
        old = Review.objects.order_by("created_at").first()
        self.line(f"Пример 3. Review.is_editable (24 ч): создан {timezone.localtime(review.created_at):%d.%m %H:%M} → {review.is_editable};"
                  f" создан {timezone.localtime(old.created_at):%d.%m %H:%M} → {old.is_editable}")
        person = Person.objects.filter(birth_date__isnull=False).order_by("-birth_date").first()
        self.line(f"Пример 4. Person.age(): {person.full_name}, род. {person.birth_date} → {person.age()} лет на {timezone.localdate()}")

    def item_1_2(self):
        self.title("1.2 class Meta: ordering")
        self.line(f"Movie.Meta.ordering    = {Movie._meta.ordering}")
        for movie in Movie.objects.all()[:5]:
            self.line(f"  {movie.views_count:>5} просм.  {movie.title}")
        self.line(f"Category.Meta.ordering = {Category._meta.ordering}: " + ", ".join(c.name for c in Category.objects.all()))
        self.line(f"Subscription.Meta.ordering = {Subscription._meta.ordering}")
        sql = str(Movie.objects.all().query)
        self.line(f"{GREY}SQL: ...{sql[sql.index('ORDER BY'):]}{RESET}")

    def item_1_3(self):
        self.title("1.3 choices в полях модели")
        for movie in Movie.objects.order_by("title")[:3]:
            self.line(f"«{movie.title}»: access='{movie.access}' → get_access_display()='{movie.get_access_display()}',"
                      f" status='{movie.status}' → '{movie.get_status_display()}', age_rating='{movie.age_rating}'")
        credit = MovieCredit.objects.select_related("person").filter(role=MovieCredit.Role.DIRECTOR).first()
        self.line(f"MovieCredit.role='{credit.role}' → '{credit.get_role_display()}' ({credit.person})")
        self.line("Movie.Access.choices = " + str(Movie.Access.choices))

    def item_1_4(self):
        self.title("1.4 related_name: обратные связи")
        genre = Category.objects.get(name="Фантастика")
        self.line(f"genre.movies.count()          → {genre.movies.count()}  (Category → Movie, related_name='movies')")
        person = Person.objects.annotate(n=Count("credits")).order_by("-n").first()
        self.line(f"person.movies.all()           → {person.full_name}: " + ", ".join(m.title for m in person.movies.all()[:4]))
        user = User.objects.get(username="tester1")
        self.line(f"user.subscriptions.active()   → {[str(s.plan.name) for s in user.subscriptions.active()]}")
        self.line(f"user.favorites.count()        → {user.favorites.count()},  user.reviews.count() → {user.reviews.count()}")
        movie = Movie.objects.get(title="Интерстеллар")
        self.line(f"movie.credits.count()         → {movie.credits.count()},  movie.reviews.count() → {movie.reviews.count()}")

    def item_1_5(self):
        self.title("1.5 filter() и двойное подчёркивание")
        qs = Movie.objects.filter(category__name="Фантастика")
        self.line(f"filter(category__name='Фантастика')           → {qs.count()} фильм.  (обращение к связанной таблице)")
        qs = Movie.objects.filter(release_year__gte=2010)
        self.line(f"filter(release_year__gte=2010)                → {qs.count()} фильм.  (метод сравнения)")
        qs = Movie.objects.filter(credits__person__full_name="Кристофер Нолан", credits__role="director")
        self.line(f"filter(credits__person__full_name='Кристофер Нолан') → " + ", ".join(m.title for m in qs))
        qs = Movie.objects.filter(countries__code="SU", duration_minutes__lt=100)
        self.line(f"filter(countries__code='SU', duration_minutes__lt=100) → " + ", ".join(m.title for m in qs))

    def item_1_6(self):
        self.title("1.6 exclude() и order_by()")
        qs = Movie.objects.published().exclude(age_rating="18+").exclude(access="subscription")
        self.line(f"exclude(age_rating='18+').exclude(access='subscription') → {qs.count()} фильм. для семейного просмотра")
        self.line("order_by('-release_year')[:4]: " + ", ".join(f"{m.title} ({m.release_year})" for m in Movie.objects.order_by("-release_year")[:4]))
        self.line("order_by('duration_minutes')[:3]: " + ", ".join(f"{m.title} {m.duration_minutes} мин" for m in Movie.objects.order_by("duration_minutes")[:3]))

    def item_1_7(self):
        self.title("1.7 собственные менеджеры, get_absolute_url, reverse")
        self.line(f"Movie.objects.published().count()    = {Movie.objects.published().count()}  (всего {Movie.objects.count()}, черновики скрыты)")
        self.line(f"Movie.objects.new_releases().count() = {Movie.objects.new_releases().count()}")
        self.line(f"Movie.objects.coming_soon().count()  = {Movie.objects.coming_soon().count()}")
        self.line(f"Movie.objects.free().count()         = {Movie.objects.free().count()}")
        self.line(f"Review.approved.count() = {Review.approved.count()}  (Review.objects.count() = {Review.objects.count()})")
        self.line(f"Subscription.objects.active().count() = {Subscription.objects.active().count()}, expiring(3) = {Subscription.objects.expiring().count()}")
        movie = Movie.objects.get(title="Матрица")
        self.line(f"movie.get_absolute_url()                      = {movie.get_absolute_url()}")
        self.line(f"reverse('movie-page', args=[{movie.pk}])            = {reverse('movie-page', args=[movie.pk])}")
        today = timezone.localdate()
        self.line(f"reverse('premieres-by-month', args=[{today.year}, '{today.month:02d}']) = {reverse('premieres-by-month', args=[today.year, f'{today.month:02d}'])}")

    def item_1_8(self):
        self.title("1.8 агрегирование и аннотирование")
        stats = Movie.objects.published().aggregate(
            total=Count("id"), views=Sum("views_count"), avg=Avg("duration_minutes"),
            longest=Max("duration_minutes"), oldest=Min("release_year"),
        )
        self.line(f"Пример 1. aggregate(): фильмов {stats['total']}, просмотров {stats['views']}, средняя длительность {stats['avg']:.0f} мин,"
                  f" самый длинный {stats['longest']} мин, самый старый {stats['oldest']} г.")
        top = Movie.objects.annotate(rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)), n=Count("reviews")).filter(n__gte=3).order_by("-rating")[:3]
        self.line("Пример 2. annotate(Avg('reviews__rating')): " + ", ".join(f"{m.title} ★{m.rating:.1f} ({m.n} отз.)" for m in top))
        persons = Person.objects.annotate(n=Count("credits")).order_by("-n", "full_name")[:3]
        self.line("Пример 3. annotate(Count('credits')): " + ", ".join(f"{p.full_name} — {p.n}" for p in persons))
        genres = Category.objects.annotate(n=Count("movies")).order_by("-n")[:3]
        self.line("Пример 4. annotate(Count('movies')): " + ", ".join(f"{g.name} — {g.n}" for g in genres))

    def item_2_3(self):
        self.title("2.3 ManyToManyField(through='MovieCredit', through_fields=('movie', 'person'))")
        field = Movie._meta.get_field("persons")
        self.line(f"Movie.persons.through = {field.remote_field.through.__name__}, through_fields = {field.remote_field.through_fields}")
        movie = Movie.objects.get(title="Начало")
        for credit in movie.credits.select_related("person"):
            self.line(f"  {credit.order}. {credit.person.full_name:<22} {credit.get_role_display():<11} {credit.character_name}")
        person = Person.objects.get(full_name="Леонардо ДиКаприо")
        self.line(f"Обратная сторона: person.movies → " + ", ".join(m.title for m in person.movies.order_by("release_year")))
        self.line(f"Таблица в БД: {MovieCredit._meta.db_table}")

    def item_2_4(self):
        self.title("2.4 select_related() и prefetch_related(): число SQL-запросов")
        with CaptureQueriesContext(connection) as plain:
            for movie in Movie.objects.all():
                _ = (movie.category.name if movie.category else "", [c.name for c in movie.countries.all()], [c.person.full_name for c in movie.credits.all()])
        with CaptureQueriesContext(connection) as optimized:
            qs = Movie.objects.select_related("category").prefetch_related("countries", "credits__person")
            for movie in qs:
                _ = (movie.category.name if movie.category else "", [c.name for c in movie.countries.all()], [c.person.full_name for c in movie.credits.all()])
        count = Movie.objects.count()
        self.line(f"Фильмов: {count}. Выводим жанр, страны и съёмочную группу.")
        self.line(f"Без оптимизации:                  {YELLOW}{len(plain)} запросов{RESET}")
        self.line(f"select_related + prefetch_related: {GREEN}{len(optimized)} запроса{RESET}")
        self.line(f"Экономия: {100 - len(optimized) * 100 // len(plain)} %")

    def item_3_1(self):
        self.title("3.1 ImageField и FileField")
        for model, name in [(Movie, "poster"), (Person, "photo"), (Movie, "subtitles")]:
            field = model._meta.get_field(name)
            self.line(f"{model.__name__}.{name}: {field.__class__.__name__}(upload_to='{field.upload_to}')")
        movie = Movie.objects.exclude(subtitles="").exclude(subtitles__isnull=True).first()
        self.line(f"В БД хранится путь: poster='{movie.poster.name}', subtitles='{movie.subtitles.name}'")
        self.line(f"URL: {movie.poster.url}  размер {movie.poster.size} байт, {movie.poster.width}×{movie.poster.height} px")
        try:
            Movie(title="t", description="d", release_year=2000, duration_minutes=1, subtitles="files/virus.exe").full_clean(exclude=["poster"])
        except ValidationError as error:
            self.line(f"FileExtensionValidator: virus.exe → {error.message_dict['subtitles'][0]}")

    def item_3_2(self):
        self.title("3.2 return redirect: код ответа и Location")
        client = Client()
        response = client.get("/movies/999999/")
        self.line(f"GET  /movies/999999/          → {response.status_code}  Location: {response['Location']}  (фильма нет)")
        response = client.get("/favorites/")
        self.line(f"GET  /favorites/ (гость)      → {response.status_code}  Location: {response['Location']}")
        client.force_login(User.objects.get(username="tester2"))
        movie = Movie.objects.published().first()
        with transaction.atomic():
            response = client.post(f"/movies/{movie.pk}/favorite/")
            transaction.set_rollback(True)
        self.line(f"POST /movies/{movie.pk}/favorite/       → {response.status_code}  Location: {response['Location']}")
        plan = SubscriptionPlan.objects.first()
        with transaction.atomic():
            response = client.post(f"/subscribe/{plan.pk}/")
            transaction.set_rollback(True)
        self.line(f"POST /subscribe/{plan.pk}/            → {response.status_code}  Location: {response['Location']}")

    def item_3_5(self):
        self.title("3.5 собственные методы модели")
        movie = Movie.objects.get(title="Интерстеллар")
        self.line(f"movie.formatted_duration      = {movie.formatted_duration}")
        self.line(f"movie.average_rating()        = {movie.average_rating():.1f}")
        self.line(f"movie.directors()             = {[p.full_name for p in movie.directors()]}")
        self.line(f"movie.days_since_premiere()   = {movie.days_since_premiere()}")
        user = User.objects.get(username="tester4")
        self.line(f"movie.is_available_for(tester4) = {movie.is_available_for(user)}  (access={movie.access})")
        plan = SubscriptionPlan.objects.get(name="Год")
        self.line(f"plan.price_per_day()          = {plan.price_per_day()} ₽ ({plan})")
        with transaction.atomic():
            sub = Subscription.objects.active().first()
            before = timezone.localtime(sub.expires_at)
            after = timezone.localtime(sub.extend(30))
            self.line(f"subscription.extend(30)       : {before:%d.%m.%Y} → {after:%d.%m.%Y}")
            transaction.set_rollback(True)

    def item_4_1(self):
        self.title("4.1 URLField: проверка адреса")
        person = Person.objects.exclude(wiki_url="").first()
        person.full_clean()
        self.line(f"«{person.wiki_url}» → корректный адрес")
        person.wiki_url = "это-не-ссылка"
        try:
            person.full_clean()
        except ValidationError as error:
            self.line(f"«это-не-ссылка» → ValidationError: {error.message_dict['wiki_url'][0]}")

    def item_4_2(self):
        self.title(f"4.2 __icontains и __contains ({connection.vendor})")
        for lookup in ["title__contains", "title__icontains"]:
            for text in ["Матрица", "матрица"]:
                found = list(Movie.objects.filter(**{lookup: text}).values_list("title", flat=True))
                self.line(f"filter({lookup}='{text}'){' ' * (18 - len(lookup))} → {found}")

    def item_4_3(self):
        self.title("4.3 values() и values_list()")
        rows = list(Category.objects.annotate(n=Count("movies")).order_by("-n").values("name", "n")[:3])
        self.line(f"Category.values('name', 'n')[:3]          → {rows}")
        self.line(f"Movie.values_list('title', 'release_year')[:2] → {list(Movie.objects.order_by('title').values_list('title', 'release_year')[:2])}")
        ids = list(Favorite.objects.filter(user__username="tester1").values_list("movie_id", flat=True))
        self.line(f"Favorite.values_list('movie_id', flat=True)  → {ids}")

    def item_4_4(self):
        self.title("4.4 count() и exists()")
        with CaptureQueriesContext(connection) as queries:
            total = Movie.objects.filter(category__name="Драма").count()
            has_18 = Movie.objects.filter(age_rating="18+").exists()
        self.line(f"Movie.objects.filter(category__name='Драма').count() = {total}")
        self.line(f"{GREY}SQL: {queries.captured_queries[0]['sql'][:150]}{RESET}")
        self.line(f"Movie.objects.filter(age_rating='18+').exists()       = {has_18}")
        self.line(f"{GREY}SQL: {queries.captured_queries[1]['sql'][:150]}{RESET}")

    def item_4_5(self):
        self.title("4.5 update() и delete() (в транзакции, с откатом)")
        with transaction.atomic():
            updated = Movie.objects.filter(category__name="Мультфильм").update(access=Movie.Access.FREE)
            self.line(f"update(access='free') для мультфильмов → изменено строк: {updated}")
            deleted = Review.objects.filter(rating__lte=5).delete()
            self.line(f"Review.objects.filter(rating__lte=5).delete() → {deleted}")
            transaction.set_rollback(True)
        self.line(f"После отката: отзывов с оценкой ≤ 5 снова {Review.objects.filter(rating__lte=5).count()}")

    def item_4_6(self):
        self.title("4.6 F-выражение, кэш и Http404")
        movie = Movie.objects.get(title="Матрица")
        with transaction.atomic():
            before = movie.views_count
            Movie.objects.filter(pk=movie.pk).update(views_count=F("views_count") + 1)
            movie.refresh_from_db()
            self.line(f"update(views_count=F('views_count') + 1): {before} → {movie.views_count}")
            transaction.set_rollback(True)
        cache.delete("demo_slow")

        def slow():
            time.sleep(0.5)
            return Movie.objects.published().count()

        started = time.perf_counter()
        cache.get_or_set("demo_slow", slow, 60)
        first = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        cache.get_or_set("demo_slow", slow, 60)
        second = (time.perf_counter() - started) * 1000
        self.line(f"cache.get_or_set: 1-й вызов {first:.0f} мс (вычисление), 2-й вызов {second:.2f} мс (из кэша {settings.CACHES['default']['BACKEND'].split('.')[-1]})")
        try:
            get_object_or_404(Movie, pk=999999)
        except Http404 as error:
            self.line(f"get_object_or_404(Movie, pk=999999) → Http404: {error}")
        logging.getLogger("django.request").setLevel(logging.ERROR)
        response = Client().get("/movies/?genre=999")
        self.line(f"GET /movies/?genre=999 → {response.status_code} (raise Http404('Жанр не найден'))")
