import re
from functools import lru_cache

from django.db.backends.signals import connection_created


@lru_cache(maxsize=256)
def _compile(pattern, escape):
    regex, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if escape and char == escape and index + 1 < len(pattern):
            regex.append(re.escape(pattern[index + 1]))
            index += 2
            continue
        regex.append(".*" if char == "%" else "." if char == "_" else re.escape(char))
        index += 1
    return re.compile("".join(regex), re.IGNORECASE | re.DOTALL)


def unicode_like(pattern, value, escape=None):
    if pattern is None or value is None:
        return None
    return _compile(pattern, escape).fullmatch(str(value)) is not None


def install_unicode_like(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        connection.connection.create_function("like", 2, unicode_like, deterministic=True)
        connection.connection.create_function("like", 3, unicode_like, deterministic=True)


connection_created.connect(install_unicode_like)
