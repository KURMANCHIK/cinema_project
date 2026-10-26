from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Category, Favorite, Movie, Playlist, Review


class BaseData:
    def make_data(self):
        cache.clear()
        self.category = Category.objects.create(name='Драма')
        self.movie = Movie.objects.create(
            title='Матрица', description='Про симуляцию', release_year=1999,
            duration_minutes=136, category=self.category,
        )
        self.other_movie = Movie.objects.create(
            title='Дюна', description='Про пустыню', release_year=2021, duration_minutes=155,
        )
        self.user = User.objects.create_user('neo', email='neo@example.com', password='pass12345')
        self.stranger = User.objects.create_user('smith', email='smith@example.com', password='pass12345')
        self.admin = User.objects.create_superuser('admin', email='admin@example.com', password='pass12345')


class MovieModelTests(BaseData, TestCase):
    def setUp(self):
        self.make_data()

    def test_release_year_validation(self):
        movie = Movie(title='Старое кино', description='-', release_year=1800, duration_minutes=10)
        with self.assertRaises(ValidationError):
            movie.full_clean()

    def test_title_and_year_are_unique(self):
        movie = Movie(title='Матрица', description='-', release_year=1999, duration_minutes=100)
        with self.assertRaises(ValidationError):
            movie.full_clean()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class MovieApiTests(BaseData, APITestCase):
    def setUp(self):
        self.make_data()
        Review.objects.create(movie=self.movie, user=self.user, text='Шедевр', rating=10)
        Review.objects.create(movie=self.movie, user=self.stranger, text='Неплохо', rating=6)

    def test_list_contains_annotations(self):
        response = self.client.get(reverse('movie-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        matrix = next(m for m in response.data['results'] if m['id'] == self.movie.id)
        self.assertEqual(matrix['avg_rating'], 8.0)
        self.assertEqual(matrix['reviews_count'], 2)
        self.assertEqual(matrix['formatted_duration'], '2 ч. 16 мин.')
        self.assertEqual(matrix['category_name'], 'Драма')

    def test_search_and_filter(self):
        response = self.client.get(reverse('movie-list'), {'search': 'пустын'})
        self.assertEqual([m['id'] for m in response.data['results']], [self.other_movie.id])
        response = self.client.get(reverse('movie-list'), {'category': self.category.id})
        self.assertEqual([m['id'] for m in response.data['results']], [self.movie.id])

    def test_detail_increments_views_and_shows_reviews(self):
        response = self.client.get(reverse('movie-detail', args=[self.movie.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['reviews']), 2)
        self.assertIn('description', response.data)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.views_count, 1)

    def test_only_admin_can_create_movie(self):
        payload = {'title': 'Новый', 'release_year': 2020, 'duration_minutes': 90, 'description': '-'}
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(reverse('movie-list'), payload).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(reverse('movie-list'), payload).status_code, status.HTTP_201_CREATED)

    def test_api_rejects_bad_release_year(self):
        self.client.force_authenticate(self.admin)
        payload = {'title': 'Ошибка', 'release_year': 1500, 'duration_minutes': 90, 'description': '-'}
        response = self.client.post(reverse('movie-list'), payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('release_year', response.data)

    def test_list_cache_is_invalidated_after_new_review(self):
        self.client.get(reverse('movie-list'))
        Review.objects.create(movie=self.other_movie, user=self.user, text='Красиво', rating=9)
        response = self.client.get(reverse('movie-list'))
        dune = next(m for m in response.data['results'] if m['id'] == self.other_movie.id)
        self.assertEqual(dune['avg_rating'], 9.0)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReviewApiTests(BaseData, APITestCase):
    def setUp(self):
        self.make_data()

    def test_anonymous_cannot_create_review(self):
        response = self.client.post(reverse('review-list'), {'movie': self.movie.id, 'text': 'ok', 'rating': 5})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_review_sends_email(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('review-list'), {'movie': self.movie.id, 'text': 'Класс', 'rating': 9})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'neo')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Матрица', mail.outbox[0].body)

    def test_forbidden_words(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('review-list'), {'movie': self.movie.id, 'text': 'Режиссёр идиот', 'rating': 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('text', response.data)

    def test_one_review_per_movie(self):
        self.client.force_authenticate(self.user)
        payload = {'movie': self.movie.id, 'text': 'Класс', 'rating': 9}
        self.client.post(reverse('review-list'), payload)
        response = self.client.post(reverse('review-list'), payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_author_or_admin_can_edit(self):
        review = Review.objects.create(movie=self.movie, user=self.user, text='Класс', rating=9)
        url = reverse('review-detail', args=[review.id])

        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.patch(url, {'rating': 1}).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.patch(url, {'rating': 7}).status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)


class FavoriteAndPlaylistApiTests(BaseData, APITestCase):
    def setUp(self):
        self.make_data()

    def test_favorite_toggle_via_movie_action(self):
        self.client.force_authenticate(self.user)
        url = reverse('movie-favorite', args=[self.movie.id])
        self.assertEqual(self.client.post(url).status_code, status.HTTP_201_CREATED)
        self.assertTrue(Favorite.objects.filter(user=self.user, movie=self.movie).exists())
        detail = self.client.get(reverse('movie-detail', args=[self.movie.id]))
        self.assertTrue(detail.data['is_favorite'])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_favorite'])
        self.assertFalse(Favorite.objects.exists())

    def test_favorites_are_private(self):
        Favorite.objects.create(user=self.stranger, movie=self.movie)
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse('favorite-list'))
        self.assertEqual(response.data['count'], 0)

    def test_playlist_flow(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('playlist-list'), {'name': 'На выходные'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        playlist_id = response.data['id']

        add_url = reverse('playlist-add-movie', args=[playlist_id])
        response = self.client.post(add_url, {'movie': self.movie.id})
        self.assertEqual(response.data['movies'], [self.movie.id])

        remove_url = reverse('playlist-remove-movie', args=[playlist_id])
        response = self.client.post(remove_url, {'movie': self.movie.id})
        self.assertEqual(response.data['movies_count'], 0)

    def test_cannot_see_foreign_playlist(self):
        playlist = Playlist.objects.create(user=self.stranger, name='Чужой')
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse('playlist-detail', args=[playlist.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WebPagesTests(BaseData, TestCase):
    def setUp(self):
        self.make_data()

    def test_index_page(self):
        response = self.client.get(reverse('catalog'), {'q': 'матр'})
        self.assertContains(response, 'Матрица')
        self.assertNotContains(response, 'Дюна')

    def test_detail_page_and_review_form(self):
        self.client.login(username='neo', password='pass12345')
        url = reverse('movie-page', args=[self.movie.id])
        self.assertContains(self.client.get(url), 'Отправить отзыв')
        response = self.client.post(url, {'rating': 8, 'text': 'Отлично'}, follow=True)
        self.assertContains(response, 'Отзыв опубликован')
        self.assertEqual(len(mail.outbox), 1)

    def test_register_page(self):
        response = self.client.post(reverse('register'), {
            'username': 'trinity', 'email': 'trinity@example.com',
            'password1': 'Strong-pass-123', 'password2': 'Strong-pass-123',
        })
        self.assertRedirects(response, reverse('home'))
        self.assertTrue(User.objects.filter(username='trinity').exists())


GOOGLE_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'APPS': [{'client_id': 'test-client-id', 'secret': 'test-secret', 'key': ''}],
    }
}


class GoogleAuthTests(TestCase):
    def test_button_hidden_without_keys(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS={'google': {'SCOPE': ['email']}}):
            response = self.client.get(reverse('login'))
        self.assertNotContains(response, 'Войти через Google')

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
    def test_button_shown_on_login_and_register(self):
        self.assertContains(self.client.get(reverse('login')), 'Войти через Google')
        self.assertContains(self.client.get(reverse('register')), 'Войти через Google')

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
    def test_login_redirects_to_google(self):
        response = self.client.post(reverse('google_login'), {'process': 'login'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.google.com', response['Location'])
        self.assertIn('client_id=test-client-id', response['Location'])
        self.assertIn('accounts%2Fgoogle%2Flogin%2Fcallback', response['Location'])

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user('neo', email='neo@example.com', password='pass12345')
        response = self.client.post(reverse('register'), {
            'username': 'other', 'email': 'NEO@example.com',
            'password1': 'Strong-pass-123', 'password2': 'Strong-pass-123',
        })
        self.assertContains(response, 'уже зарегистрирован')


class GoogleProfileTests(TestCase):
    def setUp(self):
        from allauth.socialaccount.models import SocialAccount
        self.user = User.objects.create_user('nicola', email='nicola@gmail.com', first_name='Nicola')
        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(
            user=self.user, provider='google', uid='123',
            extra_data={'name': 'Nicola G', 'email': 'nicola@gmail.com', 'picture': 'https://lh3.googleusercontent.com/a/photo'},
        )
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.movie = Movie.objects.create(title='Матрица', description='-', release_year=1999, duration_minutes=136)
        Review.objects.create(movie=self.movie, user=self.user, text='Класс', rating=9)

    def test_header_shows_google_avatar_and_name(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'https://lh3.googleusercontent.com/a/photo')
        self.assertContains(response, 'Nicola')

    def test_review_shows_author_avatar(self):
        response = self.client.get(reverse('movie-page', args=[self.movie.id]))
        self.assertContains(response, 'class="avatar avatar--sm" src="https://lh3.googleusercontent.com/a/photo"', count=2)

    def test_profile_shows_linked_google(self):
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Привязан')
        self.assertContains(response, 'Nicola G')
        self.assertContains(response, 'задайте пароль')

    def test_cannot_disconnect_without_password(self):
        self.client.post(reverse('google-disconnect'))
        self.assertTrue(self.user.socialaccount_set.exists())

    def test_disconnect_with_password(self):
        self.user.set_password('Strong-pass-123')
        self.user.save()
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.client.post(reverse('google-disconnect'))
        self.assertFalse(self.user.socialaccount_set.exists())

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
    def test_profile_offers_connect_when_not_linked(self):
        self.user.socialaccount_set.all().delete()
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Привязать Google')


import shutil
import tempfile
from datetime import timedelta
from io import BytesIO, StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from PIL import Image

from .models import Country, MovieCredit, Person, Subscription, SubscriptionPlan

TEMP_MEDIA = tempfile.mkdtemp()


def make_image():
    buffer = BytesIO()
    Image.new("RGB", (20, 30), (200, 50, 50)).save(buffer, "PNG")
    return SimpleUploadedFile("poster.png", buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class LabFeaturesTests(BaseData, TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.make_data()
        today = timezone.localdate()
        self.movie.premiere_date = today - timedelta(days=5)
        self.movie.save()
        self.soon = Movie.objects.create(
            title='Скоро', description='-', release_year=2026, duration_minutes=100,
            premiere_date=today + timedelta(days=10),
        )
        self.draft = Movie.objects.create(
            title='Черновик', description='-', release_year=2020, duration_minutes=90, status=Movie.Status.DRAFT,
        )
        self.plan = SubscriptionPlan.objects.create(name='Месяц', price=299, duration_days=30)

    def test_timezone_properties(self):
        self.assertTrue(self.movie.is_new)
        self.assertFalse(self.movie.is_coming_soon)
        self.assertTrue(self.soon.is_coming_soon)
        self.assertEqual(self.soon.days_until_premiere(), 10)

    def test_subscription_dates(self):
        subscription = Subscription.objects.create(user=self.user, plan=self.plan)
        self.assertEqual((subscription.expires_at - subscription.started_at).days, 30)
        self.assertTrue(subscription.is_active)
        self.assertEqual(subscription.price_paid, 299)
        old = Subscription.objects.create(user=self.stranger, plan=self.plan, started_at=timezone.now() - timedelta(days=40))
        self.assertFalse(old.is_active)
        self.assertEqual(list(Subscription.objects.active()), [subscription])
        subscription.extend(10)
        self.assertEqual(subscription.days_left(), 39)

    def test_review_edit_window(self):
        review = Review.objects.create(movie=self.movie, user=self.user, text='Класс', rating=9)
        self.assertTrue(review.is_editable)
        Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(hours=25))
        review.refresh_from_db()
        self.assertFalse(review.is_editable)
        self.client.login(username='neo', password='pass12345')
        self.assertEqual(self.client.get(reverse('review-edit', args=[review.pk])).status_code, 403)

    def test_manager_methods(self):
        self.assertNotIn(self.draft, Movie.objects.published())
        self.assertIn(self.movie, Movie.objects.new_releases())
        self.assertIn(self.soon, Movie.objects.coming_soon())
        self.assertNotIn(self.soon, Movie.objects.released())
        self.assertEqual(list(Movie.objects.search('симуляц')), [self.movie])
        self.assertEqual(self.movie.get_absolute_url(), f'/movies/{self.movie.pk}/')

    def test_through_model(self):
        person = Person.objects.create(full_name='Киану Ривз')
        MovieCredit.objects.create(movie=self.movie, person=person, role=MovieCredit.Role.ACTOR, character_name='Нео')
        self.assertIn(person, self.movie.persons.all())
        self.assertIn(self.movie, person.movies.all())
        response = self.client.get(reverse('person-page', args=[person.pk]))
        self.assertContains(response, 'Матрица')

    def test_home_widgets(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Новинки месяца')
        self.assertContains(response, 'Календарь премьер')
        self.assertContains(response, 'Скоро')

    def test_catalog_http404_and_month_route(self):
        self.assertEqual(self.client.get(reverse('catalog'), {'genre': 999}).status_code, 404)
        today = timezone.localdate()
        soon = self.soon.premiere_date
        response = self.client.get(f'/premieres/{soon.year}/{soon.month:02d}/')
        self.assertContains(response, 'Скоро')
        self.assertEqual(self.client.get(f'/premieres/{today.year}/13/').status_code, 404)

    def test_missing_and_draft_movie_redirect(self):
        response = self.client.get(reverse('movie-page', args=[99999]))
        self.assertRedirects(response, reverse('catalog'))
        response = self.client.get(reverse('movie-page', args=[self.draft.pk]))
        self.assertRedirects(response, reverse('catalog'))

    def test_views_counter_uses_f_expression(self):
        self.client.get(reverse('movie-page', args=[self.movie.pk]))
        self.client.get(reverse('movie-page', args=[self.movie.pk]))
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.views_count, 2)

    def test_staff_crud_on_site(self):
        self.client.login(username='admin', password='pass12345')
        country = Country.objects.create(name='США', code='US')
        response = self.client.post(reverse('movie-create'), {
            'title': 'Новый фильм', 'description': 'Описание', 'category': self.category.pk, 'countries': [country.pk],
            'release_year': 2024, 'duration_minutes': 120, 'age_rating': '12+', 'access': 'free', 'status': 'published',
            'poster': make_image(),
        })
        movie = Movie.objects.get(title='Новый фильм')
        self.assertRedirects(response, movie.get_absolute_url())
        self.assertTrue(movie.poster.name.startswith('posters/'))
        self.assertEqual(movie.created_by.username, 'admin')
        response = self.client.post(reverse('movie-edit', args=[movie.pk]), {
            'title': 'Новый фильм 2', 'description': 'Описание', 'release_year': 2024, 'duration_minutes': 125,
            'age_rating': '12+', 'access': 'free', 'status': 'published',
        })
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'Новый фильм 2')
        response = self.client.post(reverse('movie-delete', args=[movie.pk]))
        self.assertRedirects(response, reverse('manage-movies'))
        self.assertFalse(Movie.objects.filter(pk=movie.pk).exists())
        self.assertTrue(Movie.objects.filter(pk=self.movie.pk).exists())

    def test_non_staff_cannot_manage(self):
        self.client.login(username='neo', password='pass12345')
        self.assertEqual(self.client.get(reverse('manage-movies')).status_code, 403)
        self.assertEqual(self.client.post(reverse('movie-delete', args=[self.movie.pk])).status_code, 403)

    def test_subscribe_gives_access(self):
        locked = Movie.objects.create(
            title='По подписке', description='-', release_year=2020, duration_minutes=90, access=Movie.Access.SUBSCRIPTION,
        )
        self.assertFalse(locked.is_available_for(self.user))
        self.client.login(username='neo', password='pass12345')
        response = self.client.post(reverse('subscribe', args=[self.plan.pk]))
        self.assertRedirects(response, reverse('profile'))
        self.assertTrue(locked.is_available_for(self.user))

    def test_admin_pages_and_pdf(self):
        self.client.login(username='admin', password='pass12345')
        for name in ['movie', 'person', 'review', 'subscription', 'category', 'country', 'playlist', 'favorite', 'moviecredit', 'subscriptionplan']:
            self.assertEqual(self.client.get(f'/admin/cinema/{name}/').status_code, 200, name)
        response = self.client.post('/admin/cinema/movie/', {'action': 'download_pdf', '_selected_action': [self.movie.pk]})
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.client.post('/admin/cinema/movie/', {'action': 'unpublish', '_selected_action': [self.movie.pk]})
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.status, Movie.Status.DRAFT)

    def test_generate_fixtures_command(self):
        call_command('generate_fixtures', '--no-images', '--users', '3', stdout=StringIO())
        self.assertGreaterEqual(Movie.objects.count(), 30)
        self.assertGreaterEqual(Person.objects.count(), 50)
        self.assertTrue(Subscription.objects.active().exists())
