# instagram_app/urls.py

from django.urls import path
from .views import CustomSignInView,InstagramFetchData,generate_carousel,get_user_profile,get_user_posts

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    path('instagram/signin-user/', CustomSignInView.as_view(), name='token_obtain_pair'),      # Sign In
    path('instagram/signin-user/refresh/', TokenRefreshView.as_view(), name='token_refresh'),     # Refresh
    path("instagram/save-userData/", InstagramFetchData.as_view(), name="instagram-fetch-data"),
    path('instagram/generate-carousel/', generate_carousel, name='generate_carousel'),
    path('instagram/user-profile/', get_user_profile, name='get_user_profile'),
    path('instagram/user-posts/', get_user_posts, name='get_user_posts'),

]
