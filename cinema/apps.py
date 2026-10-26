from django.apps import AppConfig


class CinemaConfig(AppConfig):
    name = 'cinema'
    verbose_name = 'Кинотеатр'

    def ready(self):
        from . import signals, sqlite_unicode
