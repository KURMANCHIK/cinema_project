from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('categories', views.CategoryViewSet, basename='category')
router.register('movies', views.MovieViewSet, basename='movie')
router.register('countries', views.CountryViewSet, basename='country')
router.register('plans', views.SubscriptionPlanViewSet, basename='plan')
router.register('persons', views.PersonViewSet, basename='person')
router.register('reviews', views.ReviewViewSet, basename='review')
router.register('favorites', views.FavoriteViewSet, basename='favorite')
router.register('playlists', views.PlaylistViewSet, basename='playlist')

urlpatterns = [
    path('', include(router.urls)),
]
