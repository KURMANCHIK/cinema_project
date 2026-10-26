# Cinema — онлайн-кинотеатр (курсовой проект)

Django 6 + Django REST Framework + Bootstrap 5. Каталог фильмов, персоны и съёмочные группы, отзывы, избранное, плейлисты, подписки, админка с PDF, версия для слабовидящих и печати, Swagger, Celery, Redis, PostgreSQL.

## Запуск через Docker (основной способ)

```bash
docker compose up --build -d
docker compose exec web python manage.py generate_fixtures
```

Миграции применяются автоматически при старте контейнера `web`.

| Адрес | Что там |
|---|---|
| http://localhost:8000/ | Главная страница с виджетами |
| http://localhost:8000/movies/ | Каталог с поиском и фильтрами |
| http://localhost:8000/movies/1/ | Страница фильма (ID в адресе), печать |
| http://localhost:8000/manage/ | Управление фильмами: добавить, изменить, удалить (для сотрудников) |
| http://localhost:8000/api/ | API (браузерная версия DRF) |
| http://localhost:8000/api/docs/ | Swagger |
| http://localhost:8000/admin/ | Админка |
| http://localhost:8025/ | MailHog — письма «Спасибо за отзыв» |

После `generate_fixtures`: администратор `admin` / `admin12345`, пользователи `tester1` … `tester12` / `tester12345`.

### Если Docker Hub недоступен

Образы по умолчанию скачиваются через зеркало `mirror.gcr.io`.
Адреса образов лежат в `.env`. Если зеркало не отвечает, замени префикс на другое зеркало:

```
PYTHON_IMAGE=dockerhub.timeweb.cloud/library/python:3.12-slim
POSTGRES_IMAGE=dockerhub.timeweb.cloud/library/postgres:14
REDIS_IMAGE=dockerhub.timeweb.cloud/library/redis:alpine
MAILHOG_IMAGE=dockerhub.timeweb.cloud/mailhog/mailhog
```

Если Docker Hub у тебя работает, можно указать обычные имена: `python:3.12-slim`, `postgres:14`, `redis:alpine`, `mailhog/mailhog`.

Чистый перезапуск с удалением старой базы:

```bash
docker compose down -v
docker compose up --build -d
```

## Запуск без Docker (Windows)

Самый быстрый способ: дважды кликнуть `run_local.bat`.
Он создаст `venv`, установит зависимости, заполнит базу и запустит сервер на http://127.0.0.1:8000/.

Вручную:

Без переменной `DB_ENGINE=postgres` проект работает на SQLite.
Без `REDIS_URL` кэш хранится в памяти, а задачи Celery выполняются сразу.
Письма печатаются в консоль.

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py generate_fixtures
python manage.py runserver
```

## Вход через Google

Кнопка «Войти через Google» появляется на страницах входа и регистрации, когда заданы ключи.
Новый пользователь создаётся автоматически. Если аккаунт с таким email уже есть, Google привязывается к нему.

Как получить ключи:

1. Открой https://console.cloud.google.com/ и создай проект.
2. **APIs & Services → OAuth consent screen**. Тип — External. Заполни название и email. В **Test users** добавь свою почту.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**. Тип — Web application.
4. В **Authorized redirect URIs** добавь оба адреса:
   - `http://localhost:8000/accounts/google/login/callback/`
   - `http://127.0.0.1:8000/accounts/google/login/callback/`
5. Скопируй Client ID и Client secret в `.env`:

```
GOOGLE_CLIENT_ID=1234567890-xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
```

6. Перезапусти сервер. В Docker: `docker compose up -d --force-recreate web`.

Открывай сайт по тому же адресу, что указан в redirect URI. Иначе Google вернёт ошибку `redirect_uri_mismatch`.

На странице **Профиль** (`/profile/`) видно, привязан ли Google. Там же его можно привязать к обычному аккаунту или отвязать.
Аватар и имя из Google показываются в шапке сайта и у отзывов.

Ключи можно задать и через админку: **Social applications → Add**, провайдер Google, сайт `example.com`.

## Демонстрация лабораторных №3–6

```bash
python manage.py lab_demo --part 1
python manage.py lab_demo --part 2
python manage.py lab_demo --part 3
python manage.py lab_demo --part 4
python manage.py lab_demo --part 1 --item 1.8
```

Команда выполняет запросы по каждому пункту задания и печатает результат. Изменения данных откатываются.

## Тесты

```bash
python manage.py test cinema
```

В Docker: `docker compose exec web python manage.py test cinema`.

## API

| Метод и путь | Доступ | Описание |
|---|---|---|
| `GET /api/movies/` | все | Список: пагинация, `?search=`, `?category=`, `?year_from=`, `?year_to=`, `?min_rating=`, `?ordering=-avg_rating` |
| `GET /api/movies/{id}/` | все | Фильм с описанием и отзывами, +1 просмотр |
| `POST/PUT/PATCH/DELETE /api/movies/` | админ | Управление фильмами |
| `POST/DELETE /api/movies/{id}/favorite/` | авторизованный | Добавить / убрать из избранного |
| `GET /api/categories/` | все | Категории (изменять может админ) |
| `GET/POST /api/reviews/` | чтение — все, создание — авторизованный | Отзывы, `?movie=`, `?user=`, `?rating=` |
| `PUT/PATCH/DELETE /api/reviews/{id}/` | автор или админ | Изменение отзыва |
| `GET/POST/DELETE /api/favorites/` | владелец | Своё избранное |
| `/api/playlists/` + `add-movie/`, `remove-movie/` | владелец | Свои плейлисты |
| `/api/auth/login/`, `/api/auth/registration/` | — | Токен-авторизация (dj-rest-auth) |
| `/api/auth/google/` | — | Вход через Google (нужны `GOOGLE_CLIENT_ID` и `GOOGLE_CLIENT_SECRET` в `.env`) |

## Где что реализовано

| Требование | Где |
|---|---|
| 10 таблиц, справочники, M2M | `cinema/models.py`: справочники `Category`, `Country`, `SubscriptionPlan`; M2M `Movie.countries`, `Playlist.movies`, `Movie.persons` через `MovieCredit` |
| `ManyToManyField(through=..., through_fields=...)` | `Movie.persons` → `MovieCredit` |
| `__str__`, `verbose_name`, `Meta.ordering`, `choices`, `related_name` | все модели в `cinema/models.py` |
| `django.utils.timezone` | `Movie.is_new`, `is_coming_soon`, `Subscription.save/is_active/days_left/extend`, `Review.is_editable`, `Person.age` |
| Собственные менеджеры | `MovieQuerySet` (`published`, `released`, `new_releases`, `coming_soon`, `free`, `with_stats`, `search`), `ApprovedReviewManager`, `SubscriptionQuerySet` |
| `get_absolute_url`, `reverse` | `Movie`, `Person`, `Category`, `Review`; шаблоны и представления |
| `ImageField`, `FileField`, `URLField` | `Movie.poster`, `Person.photo`, `Movie.subtitles`, `Movie.trailer_url`, `Person.wiki_url` |
| Регулярное выражение в URL | `re_path` премьер по месяцу в `cinema/web_urls.py` |
| Админка: 11 настроек, действия, PDF | `cinema/admin.py`, `cinema/pdf.py` |
| Главная с виджетами | `HomeView` в `cinema/web_views.py`, `templates/cinema/home.html` |
| Страница фильма и CRUD | `movie_detail`, `MovieCreateView`, `MovieUpdateView`, `MovieDeleteView`, `ManageMoviesView` |
| Bootstrap 5, доступность, печать | `templates/cinema/base.html`, `static/cinema/js/site.js`, `static/cinema/css/style.css` (`@media print`) |
| Кэш Redis с инвалидацией | `cinema/cache.py`, `cinema/signals.py`, `cache.get_or_set` на главной |
| Celery: письмо после отзыва | `cinema/tasks.py` |
| Swagger, REST API | `cinema/views.py`, `cinema/urls.py` |
| OAuth2 (Google) | `_google_button.html`, `context_processors.py`, `SOCIALACCOUNT_*` |
| Демо-данные и демонстрация лаб | `generate_fixtures`, `lab_demo` в `cinema/management/commands/` |
| Тесты | `cinema/tests.py` |
