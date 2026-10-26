from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Синоним generate_fixtures: заполняет базу демонстрационными данными"

    def handle(self, *args, **options):
        call_command("generate_fixtures")
