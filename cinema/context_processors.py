from allauth.socialaccount.adapter import get_adapter
from django.conf import settings


def social_auth(request):
    try:
        google_enabled = bool(get_adapter(request).list_apps(request, provider='google'))
    except Exception:
        google_enabled = False
    return {
        'google_auth_enabled': google_enabled,
        'show_setup_hints': settings.DEBUG,
    }

