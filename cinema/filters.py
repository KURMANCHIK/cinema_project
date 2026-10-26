import django_filters

from .models import Movie


class MovieFilter(django_filters.FilterSet):
    year_from = django_filters.NumberFilter(field_name='release_year', lookup_expr='gte')
    year_to = django_filters.NumberFilter(field_name='release_year', lookup_expr='lte')
    min_rating = django_filters.NumberFilter(field_name='avg_rating', lookup_expr='gte')
    country = django_filters.CharFilter(field_name='countries__code', lookup_expr='iexact')
    person = django_filters.NumberFilter(field_name='persons__id')

    class Meta:
        model = Movie
        fields = ['category', 'release_year', 'access', 'age_rating']
