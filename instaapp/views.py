from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, permission_classes
import threading
import os
import uuid

import re
from rest_framework_simplejwt.tokens import RefreshToken
from instaapp.models import Instagram_User, InstagramPost,Question, UserAnswer,ChatThread, ChatMessage
from .serializers import InstagramUserSerializer, InstagramPostSerializer, CarouselGeneratorSerializer,QuestionSerializer, UserAnswerSerializer,ChatThreadSerializer,ChatSerializer
from instaapp.helper import save_user_profile, fetch_user_instagram_profile_data, check_instagram_credentials, get_and_save_post_detail
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
import asyncio
from cryptography.fernet import Fernet
from openai import OpenAI, AuthenticationError, RateLimitError, OpenAIError
from django.conf import settings
from .services import ConversationService
import logging
from django.db import connection

# Set up logging to console if not already configured
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

logger = logging.getLogger(__name__)

fernet = Fernet(settings.SECRET_ENCRYPTION_KEY)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

SYSTEM_PROMPT = "You are a helpful assistant that creates engaging Instagram carousel content."

logger.info('[Startup] API and view modules loaded. Logging initialized.')

class CustomSignInView(APIView):
    http_method_names = ['post']
    def post(self, request):
        """Handle user sign-in and authentication."""
        logger.info(f"[CustomSignInView] POST request received. Data: {request.data}")
        logger.info(f"[CustomSignInView] Checking database connection...")
        try:
            connection.ensure_connection()
            logger.info("[CustomSignInView] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[CustomSignInView] Database connection error: {db_exc}")
            return Response({'error': 'Database connection error.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        username = request.data.get('username')
        password = request.data.get('password')
        logger.info(f"[CustomSignInView] Params - username: {username}")
        if not username or not password:
            logger.warning("[CustomSignInView] Username or password missing.")
            return Response({'error': 'Username and password required.'}, status=status.HTTP_400_BAD_REQUEST)
        if '@' in username:
            logger.warning("[CustomSignInView] Email provided instead of username.")
            return Response({'error': 'Please enter your Instagram username, not email.'}, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(username=username, password=password)
        if user:
            logger.info(f"[CustomSignInView] User '{username}' authenticated successfully.")
            refresh = RefreshToken.for_user(user)
            has_answered = UserAnswer.objects.filter(user=user).exists()
            response_data = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'has_answered':has_answered
            }
            logger.info(f"[CustomSignInView] Response: {response_data}")
            return Response(response_data)
        else:
            logger.info(f"[CustomSignInView] User '{username}' not found or wrong password. Checking Instagram credentials.")
            try:
                user = User.objects.get(username=username)
                logger.warning(f"[CustomSignInView] Incorrect password for user '{username}'.")
                return Response({'error': 'Incorrect password'}, status=status.HTTP_401_UNAUTHORIZED)
            except User.DoesNotExist:
                result = check_instagram_credentials(username, password)
                logger.info(f"[CustomSignInView] Instagram credential check result: {result}")
                if result.get("status") == "success":
                    user = User.objects.create_user(
                        username=username,
                        password=password
                    )
                    user = authenticate(username=username, password=password)
                    Instagram_User.objects.create(
                        user=user,
                        username=username,
                        password=encrypt_password(password)
                    )
                    if user:
                        refresh = RefreshToken.for_user(user)
                        response_data = {
                            "status": "success",
                            "refresh": str(refresh),
                            "access": str(refresh.access_token),
                            'has_answered':False
                        }
                        logger.info(f"[CustomSignInView] Response: {response_data}")
                        return Response(response_data, status=status.HTTP_201_CREATED)
                    else:
                        logger.error(f"[CustomSignInView] Authentication failed after user creation for '{username}'.")
                        return Response({
                            "status": "error",
                            "message": "Authentication failed after user creation."
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                else:
                    logger.warning(f"[CustomSignInView] Instagram credential check failed: {result}")
                    return Response({
                        "status": result.get("status"),
                        "message": result.get("message")
                    }, status=status.HTTP_401_UNAUTHORIZED)
        logger.info(f"[CustomSignInView] POST request completed for username: {request.data.get('username')}")

class InstagramFetchData(APIView):
    permission_classes = [IsAuthenticated]  # ✅ only authenticated users allowed

    def post(self, request):
        """Fetch Instagram data for the authenticated user."""
        logger.info(f"[InstagramFetchData] POST request by user: {request.user.username}")
        logger.info(f"[InstagramFetchData] Request body: {request.data}")
        try:
            connection.ensure_connection()
            logger.info("[InstagramFetchData] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[InstagramFetchData] Database connection error: {db_exc}")
            return Response({'error': 'Database connection error.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        auth_username = request.user.username
        try:
            insta_user = Instagram_User.objects.get(username=auth_username)
            insta_username = insta_user.username
            logger.info(f"[InstagramFetchData] Found Instagram_User: {insta_username}")
        except Instagram_User.DoesNotExist:
            logger.error(f"[InstagramFetchData] Instagram credentials not found for user: {auth_username}")
            return Response(
                {"error": "Instagram credentials not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # ✅ Define your background task
            def background_task():
                try:
                    logger.info(f"[InstagramFetchData] Fetching Instagram profile data for: {insta_username}")
                    res = fetch_user_instagram_profile_data(insta_username)
                    logger.info(f"[InstagramFetchData] fetch_user_instagram_profile_data response: {res}")
                    if res:
                        business_discovery_res = res.get("business_discovery")
                        logger.info(f"[InstagramFetchData] business_discovery: {business_discovery_res}")
                        if business_discovery_res:
                            save_user_profile(
                                insta_username,
                                business_discovery_res.get("name"),
                                business_discovery_res.get("followers_count"),
                                business_discovery_res.get("media_count"),
                                business_discovery_res.get("profile_picture_url"),
                            )
                            logger.info(f"[InstagramFetchData] Instagram data fetched and saved for: {insta_username}")
                        else:
                            logger.warning(f"[InstagramFetchData] 'business_discovery' not found in response for: {insta_username}")
                    else:
                        logger.error(f"[InstagramFetchData] Failed to fetch Instagram profile data for: {insta_username}")
                except Exception as e:
                    logger.error(f"[InstagramFetchData] Background task error: {e}")
                get_and_save_post_detail(insta_username)
                logger.info(f"[InstagramFetchData] Post details fetched and saved for: {insta_username}")

            # ✅ Run it in background
            threading.Thread(target=background_task).start()
            logger.info(f"[InstagramFetchData] Background data fetching started for: {insta_username}")
            # ✅ Return immediately
            return Response(
                {"message": "Data fetching started in background."},
                status=status.HTTP_202_ACCEPTED
            )
        except Exception as e:
            logger.error(f"[InstagramFetchData] Failed to fetch Instagram data: {str(e)}")
            return Response(
                {"error": f"Failed to fetch Instagram data: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        logger.info(f"[InstagramFetchData] POST request completed for user: {request.user.username}")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    """Return the profile of the authenticated Instagram user."""
    logger.info(f"[get_user_profile] GET request by user: {request.user.username}")
    auth_username = request.user.username
    user = get_object_or_404(Instagram_User, username=auth_username)
    serializer = InstagramUserSerializer(user)
    logger.info(f"[get_user_profile] Profile data returned for user: {auth_username}. Response: {serializer.data}")
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_posts(request):
    """Return the top posts for the authenticated Instagram user."""
    logger.info(f"[get_user_posts] GET request by user: {request.user.username}")
    auth_username = request.user.username
    user = get_object_or_404(Instagram_User, username=auth_username)
    posts = InstagramPost.objects.filter(user=user).order_by('-likes')[:3]
    serializer = InstagramPostSerializer(posts, many=True)
    logger.info(f"[get_user_posts] Top posts returned for user: {auth_username}. Response: {serializer.data}")
    return Response(serializer.data)

def encrypt_password(plain_text):
    """Encrypt the given plain text password."""
    logger.debug("[encrypt_password] Encrypting password.")
    return fernet.encrypt(plain_text.encode()).decode()

class CarouselGeneratorView(APIView):
    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conversation_service = ConversationService()
        logger.info("[CarouselGeneratorView] Initialized.")

    def post(self, request):
        """Generate carousel content using the conversation service."""
        logger.info(f"[CarouselGeneratorView] POST request received. User: {request.user.username}, Data: {request.data}")
        try:
            data = request.data
            logger.info(f"[CarouselGeneratorView] Extracting parameters from request data: {data}")
            
            description = data.get('description')
            message_id = data.get('message_id')
            if not message_id:
                 return Response({
                    "error": "message_id is required"
                }, status=status.HTTP_400_BAD_REQUEST)
                
            content_type = data.get('content_type')
            logger.info(f"[CarouselGeneratorView] Parameters - description: {description}, content_type: {content_type}")
            
            if not description or not content_type:
                logger.warning("[CarouselGeneratorView] Missing required fields.")
                return Response({
                    "error": "Both 'description' and 'content_type' are required"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            valid_content_types = ['Humble', 'Origin', 'Product']
            if content_type not in valid_content_types:
                logger.warning(f"[CarouselGeneratorView] Invalid content_type: {content_type}")
                return Response({
                    "error": f"Invalid content_type. Must be one of: {valid_content_types}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            slides = data.get('slides', 5)
            inspiration = data.get('inspiration')
            thread_id = data.get('thread_id')
            logger.info(f"[CarouselGeneratorView] Additional parameters - slides: {slides}, inspiration: {inspiration}, thread_id: {thread_id}")
            
            if not isinstance(slides, int) or slides < 1 or slides > 10:
                logger.warning(f"[CarouselGeneratorView] Invalid slides count: {slides}")
                return Response({
                    "error": "Slides must be an integer between 1 and 10"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Log inspiration processing start
            if inspiration:
                logger.info(f"[CarouselGeneratorView] Processing inspiration content: {inspiration}")
                if self.conversation_service.scraper.is_valid_instagram_url(inspiration):
                    logger.info(f"[CarouselGeneratorView] Instagram URL detected in inspiration: {inspiration}")
                else:
                    logger.info(f"[CarouselGeneratorView] Text/Email content detected in inspiration")
            else:
                logger.info("[CarouselGeneratorView] No inspiration content provided")
            
            logger.info("[CarouselGeneratorView] Calling conversation service to generate carousel...")
            result = self.conversation_service.generate_carousel(
                description=description,
                content_type=content_type,
                slides=slides,
                inspiration=inspiration,
                thread_id=thread_id
            )
            thread_id = result.get('thread_id')
            thread, _ = ChatThread.objects.get_or_create(
                    user=request.user,
                    thread_id=message_id  # Only use your custom thread_id field
                )

            # Save user prompt
            ChatMessage.objects.create(
                thread=thread,
                sender="user",
                message=description
            )
            
            ChatMessage.objects.create(
                thread=thread,
                sender="ai",
                message="\n".join(result['carousel_content']['slides'].values())  # or json.dumps(...)
            )
            
            logger.info(f"[CarouselGeneratorView] Carousel generated successfully.")
            logger.info(f"[CarouselGeneratorView] Result details - Thread ID: {result['thread_id']}, Model used: {result['model_used']}, Inspiration processed: {result['inspiration_processed']}")
            
            response_data = {
                "success": True,
                "thread_id": result['thread_id'],
                "content_type": content_type,
                "slides_count": slides,
                "description": description,
                "carousel_content": result['carousel_content'],
                "model_used": result['model_used'],
                "inspiration_processed": bool(result.get('inspiration_processed', False))
            }
            
            logger.info(f"[CarouselGeneratorView] Sending successful response with carousel content")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"[CarouselGeneratorView] Error in carousel generation: {str(e)}", exc_info=True)
            return Response({
                "error": "An unexpected error occurred",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        logger.info(f"[CarouselGeneratorView] POST request completed for user: {request.user.username}")
        

class GetQuestionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        questions = Question.objects.all()
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)

class SubmitAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        answers = request.data.get('answers', [])
        for item in answers:
            UserAnswer.objects.update_or_create(
                user=request.user,
                question_id=item['question'],
                defaults={'answer': item['answer']}
            )
        return Response({"message": "Answers submitted successfully"})

class UserChatListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return all chat threads for the user"""
        threads = ChatThread.objects.filter(user=request.user).order_by('-created_at')
        serializer = ChatThreadSerializer(threads, many=True)
        return Response(serializer.data)

class ChatDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, thread_id):
        """Return a single thread with messages"""
        thread = get_object_or_404(ChatThread, thread_id=thread_id, user=request.user)
        serializer = ChatSerializer(thread)
        return Response(serializer.data)

class ChatThreadCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return a new unique thread_id without creating it in DB"""
        thread_id = str(uuid.uuid4())
        return Response({'new_chat_id': thread_id}, status=status.HTTP_200_OK)
