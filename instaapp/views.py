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
from .services import ConversationService,build_content_prompt,get_next_question,clean_response
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
client = OpenAI(api_key=OPENAI_API_KEY)

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
                
            logger.info(f"[CarouselGeneratorView] Parameters - description: {description}")
            
            if not description:
                logger.warning("[CarouselGeneratorView] Missing required fields.")
                return Response({
                    "error": "Both 'description' are required"
                }, status=status.HTTP_400_BAD_REQUEST)
            acutal_description = description
           
                    
    
            thread_id = data.get('thread_id')
            logger.info(f"[CarouselGeneratorView] Additional parameters -  thread_id: {thread_id}")
            
           
             # ✅ Check if user has any previous threads
            has_previous_threads = False

            if thread_id:
                logger.info("[CarouselGeneratorView] Checking for existing thread by thread_id...")
                has_previous_threads = ChatThread.objects.filter(user=request.user, thread_id=thread_id).exists()
            else:
                logger.info("[CarouselGeneratorView] No thread_id provided; setting has_previous_threads = False.")
            if not has_previous_threads:
                logger.info("[CarouselGeneratorView] First conversation detected. Building user profile summary...")

                user_answers = UserAnswer.objects.filter(user=request.user).select_related('question')
                
                if user_answers.exists():
                    summary_lines = [
                        f"- {answer.question.text.strip()}: {answer.answer.strip()}"
                        for answer in user_answers
                    ]
                    summary_text = "\n".join(summary_lines)
                    
                    logger.info(f"[CarouselGeneratorView] Onboarding summary:\n{summary_text}")
                    
                    # 🧠 Clarify that onboarding is *background only* and question is what needs the answer
                    description = (
                        "You are an assistant helping users by answering their questions clearly. "
                        "Below is some background context about the user. You may use this to guide tone or relevance, "
                        "but you should NOT mention or refer to the background directly. "
                        "Just focus on answering the user's actual question accurately and clearly.\n\n"
                        "### USER BACKGROUND (FOR CONTEXT ONLY, DO NOT MENTION) ###\n"
                        f"{summary_text}\n\n"
                        "### USER QUESTION ###\n"
                        f"{description}"
                    )

            
            # Log inspiration processing start
           
            logger.info("[CarouselGeneratorView] Calling conversation service to generate carousel...")
            result = self.conversation_service.generate_carousel(
                description=description,
                thread_id=thread_id
            )
            thread_id = result.get('thread_id')
            thread, _ = ChatThread.objects.get_or_create(
                    user=request.user,
                    thread_id=thread_id  # Only use your custom thread_id field
                )

            # Save user prompt
            ChatMessage.objects.create(
                thread=thread,
                sender="user",
                message=acutal_description
            )
            
            ChatMessage.objects.create(
                thread=thread,
                sender="ai",
                message="\n".join(result['carousel_content']['slides'])  # or json.dumps(...)
            )
            
            logger.info(f"[CarouselGeneratorView] Carousel generated successfully.")
            logger.info(f"[CarouselGeneratorView] Result details - Thread ID: {result['thread_id']}, Model used: {result['model_used']}")
            carousel_content = result['carousel_content']['slides']
            cleaned_content = [para.strip() for para in carousel_content if para.strip()]     
            full_text = " ".join(cleaned_content)    
            response_data = {
                "success": True,
                "thread_id": thread_id,
                "description": acutal_description,
                "carousel_content": full_text,
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

class ContentChatView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        data = request.data
        prompt = data.get('prompt', '').strip()
        thread_id = data.get('thread_id', '').strip()

        # Create or get thread
        if not thread_id:
            thread_id = str(uuid.uuid4())
        thread, created = ChatThread.objects.get_or_create(
            user=request.user,
            thread_id=thread_id
        )

        # Init state if needed
        state = thread.state or {
            'step': 'initial',
            'content_type': None,
            'goal': None,
            'data': {},
            'content_generated': False
        }

        # Store user message
        ChatMessage.objects.create(
            thread=thread,
            sender="user",
            message=prompt
        )

        # Determine next question
        next_response = get_next_question(state, prompt)

        # Update state
        new_state_updates = {
            'step': next_response['next_step'],
            'data': {**state.get('data', {}), 'last_response': prompt}
        }
        if 'content_type_selected' in next_response['next_step']:
            new_state_updates['content_type'] = prompt.lower()
        if 'goal_selected' in next_response['next_step']:
            new_state_updates['goal'] = prompt.lower()

        # Save updated state
        thread.state = {**state, **new_state_updates}
        thread.save()

        # Generate AI response if needed
        if (next_response['next_step'] == 'generate_content' or 
            next_response.get('needs_ai_response') or 
            next_response.get('conversation_mode')):

            # Build content_prompt as before...
            content_prompt = build_content_prompt(next_response, thread.state, prompt)

            # Call AI
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content_prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            ai_response = clean_response(response.choices[0].message.content)

            # Store AI message
            ChatMessage.objects.create(
                thread=thread,
                sender="ai",
                message=ai_response
            )

            # Possibly update state
            if next_response['next_step'] == 'generate_content':
                thread.state['content_generated'] = True
            elif next_response.get('conversation_mode'):
                thread.state['step'] = 'smart_conversation'
            thread.save()

            return Response({
                'thread_id': thread.thread_id,
                'response': ai_response,
                'error': None
            })
        
        
        # Otherwise: structured assistant question + options
        assistant_reply = clean_response(next_response['message'])
        if 'options' in next_response:
            options_text = "\n\nOptions:\n" + "\n".join([f"- {option}" for option in next_response['options']])
            assistant_reply += options_text


        # Otherwise: structured question
        ChatMessage.objects.create(
            thread=thread,
            sender="ai",
            message=assistant_reply
        )

        return Response({
            'thread_id': thread.thread_id,
            'response': assistant_reply,
            'error': None
        })
