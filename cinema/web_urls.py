from django.contrib.auth import views as auth_views
from django.urls import path, re_path

from . import web_views
from .forms import LoginForm

urlpatterns = [
    path('', web_views.HomeView.as_view(), name='home'),
    path('movies/', web_views.CatalogView.as_view(), name='catalog'),
    path('movies/<int:pk>/', web_views.movie_detail, name='movie-page'),
    path('movies/<int:pk>/favorite/', web_views.toggle_favorite, name='movie-page-favorite'),
    re_path(
        r'^premieres/(?P<year>[0-9]{4})/(?P<month>0[1-9]|1[0-2])/$',
        web_views.premieres_by_month,
        name='premieres-by-month',
    ),
    path('persons/<int:pk>/', web_views.person_detail, name='person-page'),
    path('reviews/<int:pk>/edit/', web_views.ReviewUpdateView.as_view(), name='review-edit'),
    path('reviews/<int:pk>/delete/', web_views.ReviewDeleteView.as_view(), name='review-delete'),
    path('manage/', web_views.ManageMoviesView.as_view(), name='manage-movies'),
    path('manage/movies/add/', web_views.MovieCreateView.as_view(), name='movie-create'),
    path('manage/movies/<int:pk>/edit/', web_views.MovieUpdateView.as_view(), name='movie-edit'),
    path('manage/movies/<int:pk>/delete/', web_views.MovieDeleteView.as_view(), name='movie-delete'),
    path('subscribe/<int:plan_id>/', web_views.subscribe, name='subscribe'),
    path('favorites/', web_views.favorites, name='favorites'),
    path('login/', auth_views.LoginView.as_view(template_name='cinema/login.html', authentication_form=LoginForm), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', web_views.register, name='register'),
    path('profile/', web_views.profile, name='profile'),
    path('profile/google/disconnect/', web_views.google_disconnect, name='google-disconnect'),
]
