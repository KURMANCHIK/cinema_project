from django import template

register = template.Library()


def find_google_account(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    for account in user.socialaccount_set.all():
        if account.provider == 'google':
            return account
    return None


@register.filter
def google_avatar(user):
    account = find_google_account(user)
    return account.get_avatar_url() if account else ''


@register.filter
def display_name(user):
    return user.get_full_name() or user.username


@register.inclusion_tag('cinema/_avatar.html')
def avatar(user, size='md'):
    return {'url': google_avatar(user), 'letter': display_name(user)[:1].upper(), 'size': size}
