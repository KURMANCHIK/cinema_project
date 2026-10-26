from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, F, Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .cache import build_movies_key
from .filters import MovieFilter
from .models import Category, Country, Favorite, Movie, Person, Playlist, Review, SubscriptionPlan
from .permissions import IsAdminOrAuthor, IsAdminOrReadOnly, IsOwner
from .serializers import (
    CategorySerializer,
    CountrySerializer,
    PersonSerializer,
    SubscriptionPlanSerializer,
    FavoriteSerializer,
    MovieDetailSerializer,
    MovieSerializer,
    PlaylistMovieSerializer,
    PlaylistSerializer,
    ReviewSerializer,
)
from .tasks import send_thank_you_email


def movies_with_stats(user, include_drafts=False):
    queryset = Movie.objects.all() if include_drafts else Movie.objects.published()
    return queryset.with_related().with_stats(user)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    search_fields = ['name']


class MovieViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = MovieFilter
    search_fields = ['title', 'description']
    ordering_fields = ['title', 'release_year', 'views_count', 'avg_rating']
    ordering = ['-views_count', 'title']

    def get_queryset(self):
        queryset = movies_with_stats(self.request.user, include_drafts=self.request.user.is_staff)
        if self.action == 'retrieve':
            return queryset.prefetch_related('reviews__user', 'credits__person')
        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return MovieDetailSerializer
        return MovieSerializer

    def list(self, request, *args, **kwargs):
        key = build_movies_key(request)
        data = cache.get(key)
        if data is None:
            data = super().list(request, *args, **kwargs).data
            cache.set(key, data, settings.CACHE_TTL)
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        Movie.objects.filter(pk=kwargs['pk']).update(views_count=F('views_count') + 1)
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(request=None, responses={201: None, 204: None})
    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAuthenticated])
    def favorite(self, request, pk=None):
        movie = self.get_object()
        if request.method == 'POST':
            _, created = Favorite.objects.get_or_create(user=request.user, movie=movie)
            code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            return Response({'is_favorite': True}, status=code)
        Favorite.objects.filter(user=request.user, movie=movie).delete()
        return Response({'is_favorite': False}, status=status.HTTP_200_OK)


class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    pagination_class = None


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    pagination_class = None


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Person.objects.annotate(movies_count=Count('movies', distinct=True)).order_by('full_name')
    serializer_class = PersonSerializer
    search_fields = ['full_name']
    ordering_fields = ['full_name', 'movies_count']


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAdminOrAuthor]
    filterset_fields = ['movie', 'user', 'rating']
    ordering_fields = ['created_at', 'rating']

    def get_queryset(self):
        queryset = Review.objects.select_related('user', 'movie')
        user = self.request.user
        if user.is_staff:
            return queryset
        if user.is_authenticated:
            return queryset.filter(Q(is_approved=True) | Q(user=user))
        return queryset.filter(is_approved=True)

    def perform_create(self, serializer):
        review = serializer.save(user=self.request.user)
        if self.request.user.email:
            send_thank_you_email.delay(self.request.user.email, review.movie.title)


class FavoriteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                      mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Favorite.objects.none()
        return Favorite.objects.filter(user=self.request.user).select_related('movie')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PlaylistViewSet(viewsets.ModelViewSet):
    serializer_class = PlaylistSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Playlist.objects.none()
        return Playlist.objects.filter(user=self.request.user).prefetch_related('movies')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(request=PlaylistMovieSerializer, responses=PlaylistSerializer)
    @action(detail=True, methods=['post'], url_path='add-movie')
    def add_movie(self, request, pk=None):
        return self._change_movies(request, add=True)

    @extend_schema(request=PlaylistMovieSerializer, responses=PlaylistSerializer)
    @action(detail=True, methods=['post'], url_path='remove-movie')
    def remove_movie(self, request, pk=None):
        return self._change_movies(request, add=False)

    def _change_movies(self, request, add):
        playlist = self.get_object()
        serializer = PlaylistMovieSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movie = serializer.validated_data['movie']
        if add:
            playlist.movies.add(movie)
        else:
            playlist.movies.remove(movie)
        return Response(PlaylistSerializer(self.get_queryset().get(pk=playlist.pk)).data)


class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.GOOGLE_CALLBACK_URL
