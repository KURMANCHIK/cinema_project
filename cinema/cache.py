from django.core.cache import cache

MOVIES_VERSION_KEY = 'movies:version'


def get_movies_version():
    version = cache.get(MOVIES_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(MOVIES_VERSION_KEY, version, None)
    return version


def build_movies_key(request):
    user_part = request.user.pk if request.user.is_authenticated else 'anon'
    return f'movies:v{get_movies_version()}:{user_part}:{request.get_full_path()}'


def invalidate_movies_cache():
    try:
        cache.incr(MOVIES_VERSION_KEY)
    except ValueError:
        cache.set(MOVIES_VERSION_KEY, 2, None)
