from django.urls import path
from .views import CustomSignInView,InstagramFetchData,get_user_profile,get_user_posts,CarouselGeneratorView,GetQuestionsView,SubmitAnswersView,UserChatListView,ChatDetailView,ChatThreadCreateView,ContentChatView

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    path('instagram/signin-user/', CustomSignInView.as_view(), name='token_obtain_pair'),      # Sign In
    path('instagram/signin-user/refresh/', TokenRefreshView.as_view(), name='token_refresh'),     # Refresh
    path("instagram/save-userData/", InstagramFetchData.as_view(), name="instagram-fetch-data"),
    # path('instagram/generate-carousel/', CarouselGeneratorView.as_view(), name='generate_carousel'),
    path('instagram/user-profile/', get_user_profile, name='get_user_profile'),
    path('instagram/user-posts/', get_user_posts, name='get_user_posts'),
    path('instagram/questions/', GetQuestionsView.as_view(), name='get_questions'),
    path('instagram/submit-answers/', SubmitAnswersView.as_view(), name='submit_answers'),
    path('instagram/chats/', UserChatListView.as_view(), name='user_chats'),
    path('instagram/chats/new/', ChatThreadCreateView.as_view(), name='new_chat'),
    path('instagram/chats/<str:thread_id>/', ChatDetailView.as_view(), name='chat_detail'),
    path('instagram/generate-carousel/', ContentChatView.as_view(), name='content-chat'),


]
