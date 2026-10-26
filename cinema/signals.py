from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_movies_cache
from .models import Category, Country, Favorite, Movie, MovieCredit, Person, Review


@receiver([post_save, post_delete], sender=Movie)
@receiver([post_save, post_delete], sender=Review)
@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Favorite)
@receiver([post_save, post_delete], sender=Person)
@receiver([post_save, post_delete], sender=MovieCredit)
@receiver([post_save, post_delete], sender=Country)
@receiver(m2m_changed, sender=Movie.countries.through)
def reset_movies_cache(sender, **kwargs):
    invalidate_movies_cache()
