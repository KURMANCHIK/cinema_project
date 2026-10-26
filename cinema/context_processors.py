from allauth.socialaccount.adapter import get_adapter
from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .models import Favorite


def social_auth(request):
    try:
        google_enabled = bool(get_adapter(request).list_apps(request, provider='google'))
    except Exception:
        google_enabled = False
    return {
        'google_auth_enabled': google_enabled,
        'show_setup_hints': settings.DEBUG,
    }


def favorites(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'favorite_ids': set()}
    return {
        'favorite_ids': SimpleLazyObject(
            lambda: set(Favorite.objects.filter(user=user).values_list('movie_id', flat=True))
        )
    }
