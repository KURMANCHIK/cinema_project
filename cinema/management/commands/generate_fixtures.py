import random
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker
from PIL import Image, ImageDraw, ImageFont

from cinema.cache import invalidate_movies_cache
from cinema.models import (
    Category, Country, Favorite, Movie, MovieCredit, Person, Playlist, Review, Subscription, SubscriptionPlan,
)

from .fixtures_data import COUNTRIES, GENRES, MOVIES, PERSONS, PLANS, REVIEW_TEXTS, SUBTITLES

FONT_DIR = Path(__file__).resolve().parents[2] / "fonts"
PALETTES = {
    "Фантастика": ((20, 40, 90), (40, 170, 200)),
    "Драма": ((60, 30, 50), (190, 110, 90)),
    "Боевик": ((70, 15, 15), (230, 90, 40)),
    "Комедия": ((200, 120, 20), (250, 210, 90)),
    "Триллер": ((15, 20, 30), (90, 100, 120)),
    "Мультфильм": ((30, 120, 90), (160, 220, 120)),
    "Криминал": ((25, 25, 25), (150, 30, 40)),
    "Мелодрама": ((120, 30, 80), (240, 140, 170)),
    "Детектив": ((30, 40, 40), (120, 140, 110)),
}


def font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def wrap(draw, text, fnt, width):
    words, lines, line = text.split(), [], ""
    for word in words:
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=fnt) <= width:
            line = probe
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def make_poster(title, year, genre, seed):
    rnd = random.Random(seed)
    top, bottom = PALETTES.get(genre, ((30, 30, 60), (120, 120, 160)))
    width, height = 400, 600
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    for _ in range(6):
        r = rnd.randint(40, 160)
        x, y = rnd.randint(-40, width), rnd.randint(40, height - 200)
        shade = tuple(min(255, c + 40) for c in bottom)
        draw.ellipse([x - r, y - r, x + r, y + r], outline=shade, width=3)
    draw.rectangle([0, height - 210, width, height], fill=(10, 10, 14))
    title_font = font(38 if len(title) < 14 else 30)
    y = height - 190
    for line in wrap(draw, title.upper(), title_font, width - 40)[:3]:
        draw.text((20, y), line, font=title_font, fill=(255, 255, 255))
        y += title_font.size + 8
    draw.text((20, height - 46), f"{genre.upper()} · {year}", font=font(18, bold=False), fill=(200, 200, 210))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return ContentFile(buffer.getvalue())


def make_photo(name, seed):
    rnd = random.Random(seed)
    hue = rnd.choice([(229, 72, 77), (60, 120, 200), (40, 150, 110), (150, 80, 200), (210, 140, 40)])
    image = Image.new("RGB", (300, 300), (24, 27, 36))
    draw = ImageDraw.Draw(image)
    draw.ellipse([20, 20, 280, 280], fill=hue)
    initials = "".join(part[0] for part in name.replace("-", " ").split()[:2]).upper()
    fnt = font(96)
    w = draw.textlength(initials, font=fnt)
    draw.text(((300 - w) / 2, 95), initials, font=fnt, fill=(255, 255, 255))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = "Заполняет базу демонстрационными данными: жанры, страны, персоны, фильмы, отзывы, подписки"

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=12)
        parser.add_argument("--no-images", action="store_true", help="Не генерировать постеры и фото")

    @transaction.atomic
    def handle(self, *args, **options):
        rnd = random.Random(2026)
        fake = Faker("ru_RU")
        Faker.seed(2026)
        today = timezone.localdate()
        images = not options["no_images"]

        Subscription.objects.all().delete()
        Favorite.objects.all().delete()
        Playlist.objects.all().delete()
        Review.objects.all().delete()
        MovieCredit.objects.all().delete()
        Movie.objects.all().delete()
        Person.objects.all().delete()

        genres = {}
        for name, description in GENRES.items():
            genres[name], _ = Category.objects.update_or_create(name=name, defaults={"description": description})
        countries = {}
        for name, code in COUNTRIES:
            countries[code], _ = Country.objects.update_or_create(code=code, defaults={"name": name})
        plans = []
        for name, price, days, description in PLANS:
            plan, _ = SubscriptionPlan.objects.update_or_create(
                name=name, defaults={"price": price, "duration_days": days, "description": description, "is_active": True}
            )
            plans.append(plan)

        admin, created = User.objects.get_or_create(
            username="admin", defaults={"email": "admin@cinema.local", "first_name": "Никита", "last_name": "Волков", "is_staff": True, "is_superuser": True}
        )
        if created:
            admin.set_password("admin12345")
            admin.save()

        users = []
        for index in range(1, options["users"] + 1):
            male = index % 2 == 1
            first = fake.first_name_male() if male else fake.first_name_female()
            last = fake.last_name_male() if male else fake.last_name_female()
            user, created = User.objects.get_or_create(
                username=f"tester{index}",
                defaults={"email": f"tester{index}@example.com", "first_name": first, "last_name": last},
            )
            if created:
                user.set_password("tester12345")
                user.save()
            users.append(user)

        names = {name for movie in MOVIES for name, _, _ in movie["credits"]}
        persons = {}
        for index, name in enumerate(sorted(names)):
            birth, bio = PERSONS.get(name, (None, ""))
            slug = name.replace(" ", "_")
            person = Person(
                full_name=name,
                birth_date=date.fromisoformat(birth) if birth else None,
                biography=bio,
                wiki_url=f"https://ru.wikipedia.org/wiki/{slug}",
            )
            if images:
                person.photo.save(f"person_{index + 1}.jpg", make_photo(name, index), save=False)
            person.save()
            persons[name] = person

        offsets = list(range(-1800, -60, 45))
        rnd.shuffle(offsets)
        movies = []
        for index, data in enumerate(MOVIES):
            if index < 6:
                premiere = today - timedelta(days=rnd.randint(1, 25))
            elif index < 11:
                premiere = today + timedelta(days=rnd.randint(3, 50))
            else:
                premiere = today + timedelta(days=offsets[index % len(offsets)])
            premiere = max(premiere, date(data["year"], 1, 1) + timedelta(days=200))
            movie = Movie(
                title=data["title"],
                original_title=data["original"],
                description=data["description"],
                release_year=data["year"],
                premiere_date=premiere,
                duration_minutes=data["minutes"],
                category=genres[data["genre"]],
                age_rating=data["age"],
                access=Movie.Access.FREE if index % 3 == 0 else Movie.Access.SUBSCRIPTION,
                status=Movie.Status.DRAFT if index == len(MOVIES) - 1 else Movie.Status.PUBLISHED,
                trailer_url=f"https://www.youtube.com/results?search_query={data['original'] or data['title']}+trailer".replace(" ", "+"),
                views_count=rnd.randint(150, 6000),
                created_by=admin,
                created_at=timezone.now() - timedelta(days=len(MOVIES) - index),
            )
            if images:
                movie.poster.save(f"poster_{index + 1}.jpg", make_poster(data["title"], data["year"], data["genre"], index), save=False)
            if index % 4 == 0:
                movie.subtitles.save(f"subtitles_{index + 1}.srt", ContentFile(SUBTITLES.format(title=data["title"]).encode("utf-8")), save=False)
            movie.save()
            movie.countries.set([countries[code] for code in data["countries"]])
            for order, (name, role, character) in enumerate(data["credits"], start=1):
                MovieCredit.objects.create(movie=movie, person=persons[name], role=role, character_name=character, order=order)
            movies.append(movie)

        published = [movie for movie in movies if movie.status == Movie.Status.PUBLISHED and movie.premiere_date <= today]
        reviews = 0
        for user in users:
            for movie in rnd.sample(published, k=6):
                rating = rnd.choices([10, 9, 8, 7, 6, 5], weights=[3, 4, 4, 2, 1, 1])[0]
                review = Review.objects.create(
                    movie=movie, user=user, rating=rating, text=rnd.choice(REVIEW_TEXTS[rating]),
                    is_approved=rnd.random() > 0.08,
                )
                hours = rnd.randint(1, 20) if reviews % 9 == 0 else rnd.randint(30, 24 * 90)
                Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(hours=hours))
                reviews += 1

        for user in users:
            for movie in rnd.sample(published, k=4):
                Favorite.objects.create(user=user, movie=movie, created_at=timezone.now() - timedelta(days=rnd.randint(0, 60)))
            playlist = Playlist.objects.create(user=user, name="Посмотреть позже", is_public=rnd.random() > 0.5)
            playlist.movies.set(rnd.sample(movies[:-1], k=5))

        now = timezone.now()
        for index, user in enumerate(users):
            plan = plans[index % len(plans)]
            if index % 4 == 3:
                started = now - timedelta(days=plan.duration_days + 10)
            elif index % 4 == 2:
                started = now - timedelta(days=plan.duration_days - 2)
            else:
                started = now - timedelta(days=rnd.randint(1, max(1, plan.duration_days // 2)))
            Subscription.objects.create(user=user, plan=plan, started_at=started, auto_renew=index % 2 == 0)
        Subscription.objects.create(user=users[0], plan=plans[1], started_at=now - timedelta(days=200))

        invalidate_movies_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Готово: жанров {len(genres)}, стран {len(countries)}, тарифов {len(plans)}, персон {len(persons)}, "
            f"фильмов {len(movies)}, отзывов {reviews}, пользователей {len(users)} (+ admin). "
            "Пароли: admin / admin12345, tester1…tester{} / tester12345".format(len(users))
        ))
