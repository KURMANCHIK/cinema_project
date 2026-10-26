from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_thank_you_email(user_email, movie_title):
    send_mail(
        'Спасибо за отзыв!',
        f'Ваш отзыв на "{movie_title}" опубликован.',
        settings.DEFAULT_FROM_EMAIL,
        [user_email],
    )
