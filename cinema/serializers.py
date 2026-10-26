import re

from rest_framework import serializers

from .models import Category, Country, Favorite, Movie, MovieCredit, Person, Playlist, Review, SubscriptionPlan

FORBIDDEN_WORDS = ['дурак', 'идиот', 'спам']
FORBIDDEN_PATTERN = re.compile(r'\b(' + '|'.join(FORBIDDEN_WORDS) + r')\w*', re.IGNORECASE)


def contains_forbidden_words(text):
    return bool(FORBIDDEN_PATTERN.search(text))


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name', 'code']


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'price', 'duration_days', 'description']


class PersonSerializer(serializers.ModelSerializer):
    movies_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Person
        fields = ['id', 'full_name', 'birth_date', 'photo', 'wiki_url', 'movies_count']


class CreditSerializer(serializers.ModelSerializer):
    person = serializers.CharField(source='person.full_name', read_only=True)
    person_id = serializers.IntegerField(read_only=True)
    role = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = MovieCredit
        fields = ['person_id', 'person', 'role', 'character_name']


class ReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'movie', 'user', 'username', 'text', 'rating', 'created_at']
        read_only_fields = ['user', 'created_at']

    def validate_text(self, value):
        if contains_forbidden_words(value):
            raise serializers.ValidationError("Комментарий содержит запрещенные слова!")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        if self.instance is None and request and request.user.is_authenticated:
            if Review.objects.filter(user=request.user, movie=attrs['movie']).exists():
                raise serializers.ValidationError("Вы уже оставили отзыв на этот фильм.")
        if self.instance is not None and 'movie' in attrs and attrs['movie'] != self.instance.movie:
            raise serializers.ValidationError({"movie": "Нельзя перенести отзыв на другой фильм."})
        return attrs


class MovieSerializer(serializers.ModelSerializer):
    formatted_duration = serializers.SerializerMethodField()
    avg_rating = serializers.FloatField(read_only=True)
    reviews_count = serializers.IntegerField(read_only=True)
    is_favorite = serializers.BooleanField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    countries = serializers.SlugRelatedField(many=True, slug_field='name', queryset=Country.objects.all(), required=False)
    is_new = serializers.BooleanField(read_only=True)

    class Meta:
        model = Movie
        fields = [
            'id', 'title', 'original_title', 'release_year', 'premiere_date', 'duration_minutes',
            'formatted_duration', 'category', 'category_name', 'countries', 'age_rating', 'access', 'status',
            'poster', 'trailer_url', 'views_count', 'avg_rating', 'reviews_count', 'is_favorite', 'is_new',
        ]
        read_only_fields = ['views_count', 'poster']
        extra_kwargs = {'duration_minutes': {'write_only': True}, 'category': {'write_only': True}}

    def get_formatted_duration(self, obj) -> str:
        hours, minutes = divmod(obj.duration_minutes, 60)
        return f"{hours} ч. {minutes} мин."

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Название не может быть пустым.")
        return value


class MovieDetailSerializer(MovieSerializer):
    reviews = serializers.SerializerMethodField()
    credits = CreditSerializer(many=True, read_only=True)

    def get_reviews(self, obj) -> list:
        approved = [review for review in obj.reviews.all() if review.is_approved]
        return ReviewSerializer(approved, many=True, context=self.context).data

    class Meta(MovieSerializer.Meta):
        fields = MovieSerializer.Meta.fields + ['description', 'credits', 'reviews']


class FavoriteSerializer(serializers.ModelSerializer):
    movie_title = serializers.CharField(source='movie.title', read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'movie', 'movie_title']

    def validate_movie(self, value):
        user = self.context['request'].user
        if Favorite.objects.filter(user=user, movie=value).exists():
            raise serializers.ValidationError("Фильм уже в избранном.")
        return value


class PlaylistSerializer(serializers.ModelSerializer):
    movies = serializers.PrimaryKeyRelatedField(many=True, queryset=Movie.objects.all(), required=False)
    movies_count = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = ['id', 'name', 'movies', 'movies_count']

    def get_movies_count(self, obj) -> int:
        return len(obj.movies.all())


class PlaylistMovieSerializer(serializers.Serializer):
    movie = serializers.PrimaryKeyRelatedField(queryset=Movie.objects.all())
