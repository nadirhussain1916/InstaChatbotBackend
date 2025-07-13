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
from instaapp.models import Instagram_User, InstagramPost,onBoardingAnswer,ChatThread, ChatMessage
from .serializers import InstagramUserSerializer, InstagramPostSerializer, CarouselGeneratorSerializer,ChatThreadSerializer,ChatSerializer
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
from .constant import REELS_SYSTEM_PROMPT,EMAIL_SYSTEM_PROMPT,CAROUSEL_SYSTEM_PROMPT,GENERIC_SYSTEM_PROMPT
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
            has_answered = onBoardingAnswer.objects.filter(user=user).exists()
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

                user_answers = onBoardingAnswer.objects.filter(user=request.user)
                
                if user_answers.exists():
                    summary_lines = [
                            f"- {answer.question.strip()}: {answer.answer.strip()}"
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
        

class onBoardingAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        answers = request.data.get('answers', [])
        for item in answers:
            question_text = item.get('question')
            answer_text = item.get('answer')

            onBoardingAnswer.objects.update_or_create(
                user=request.user,
                question=question_text,
                defaults={'answer': answer_text}
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
    
    def delete(self, request, thread_id):
        """Delete the thread"""
        thread = get_object_or_404(ChatThread, thread_id=thread_id, user=request.user)
        thread.delete()
        return Response({'message': 'Thread deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)


def clean_ai_text(text):
    # Remove **bold**, *italic*, _italic_
    text = re.sub(r'(\*\*|\*|_)(.*?)\1', r'\2', text)

    # Remove Slide lines like "Slide 1 (Hook):" or "Slide 2:"
    text = re.sub(r'^\s*Slide\s*\d+(\s*\(.*?\))?:?\s*', '', text, flags=re.MULTILINE)

    # Remove numbered or bulleted lists like "1. ", "- ", "• "
    text = re.sub(r'^\s*(\d+\.|\-|\•)\s*', '', text, flags=re.MULTILINE)

    # Remove all double quotes
    text = text.replace('"', '')

    # Collapse multiple newlines into two
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip any leading/trailing whitespace
    return text.strip()


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
        new_chat = data.get('new_chat', {})
        prompt = data.get('prompt', '').strip()
        thread_id = data.get('thread_id', '').strip()
        
        if not thread_id and not prompt:
            user_answers = onBoardingAnswer.objects.filter(user=request.user)

            if not user_answers.exists():
                return Response({"error": "No onboarding data found for user."}, status=status.HTTP_400_BAD_REQUEST)

            summary_lines = [
                f"- {answer.question.strip()}: {answer.answer.strip()}"
                for answer in user_answers
            ]
            summary_text = "\n".join(summary_lines)

            logger.info(f"[ContentChatView] Onboarding summary used as first prompt:\n{summary_text}")

                # Build prompt that guides the AI to produce a personalized summary + welcome message
            prompt = (
                "The following is information collected from the user during onboarding. "
                "Based on this, generate a personalized summary of the user along with a friendly welcome message. "
                "Do not list the questions directly — instead, rephrase them into a natural summary that shows you understand the user. "
                "Then suggest how you can assist them going forward.\n\n"
                f"{summary_text}"
            )

            # Also generate a new thread id
            thread_id = str(uuid.uuid4())
            thread, _ = ChatThread.objects.get_or_create(
                user=request.user,
                thread_id=thread_id,
                defaults={'title': "Onboarding summary"}
            )

            # Directly build conversation history with only this
            conversation_history = f"User onboarding info:\n{summary_text}\n\nAI:"

            SYSTEM_PROMPT = GENERIC_SYSTEM_PROMPT

            # Call AI
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": conversation_history}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            ai_response = clean_response(response.choices[0].message.content)
            cleaned_ai_response = clean_ai_text(ai_response)

            # Save AI response to thread
            ChatMessage.objects.create(
                thread=thread,
                sender="ai",
                message=cleaned_ai_response
            )

            return Response({
                "thread_id": thread.thread_id,
                "response": cleaned_ai_response,
                "prompt": "",
                "error": None
            })

        if not prompt:
            return Response({'error': 'prompt is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Create or get thread
        if not thread_id:
            thread_id = str(uuid.uuid4())

        thread, created = ChatThread.objects.get_or_create(
            user=request.user,
            thread_id=thread_id,
            defaults={'title': prompt}
        )

        if created:
            print(f"New thread created with title from prompt: {prompt}")
        elif not thread.title or thread.title == "Onboarding summary":
            thread.title = prompt
            thread.save()

        # ✅ Build a combined conversation history for the prompt
        conversation_history = ""

        if new_chat:
            conversation_history += (
                "Below are some previous questions and answers from the user for your interest only. "
                "Remember these for context, but do not answer them again:\n"
            )
            for question, answer in new_chat.items():
                if question and answer:
                    ChatMessage.objects.create(thread=thread, sender="ai", message=question)
                    ChatMessage.objects.create(thread=thread, sender="user", message=answer)
                    conversation_history += f"User: {question}\nAI: {answer}\n"
    

        # ✅ Determine system prompt type based on first question/answer
        SYSTEM_PROMPT = ""
        if new_chat:
            first_answer = next(iter(new_chat.values())).lower()
            if re.search(r"\breel", first_answer):
                SYSTEM_PROMPT = REELS_SYSTEM_PROMPT
                print("✅ Selected SYSTEM_PROMPT: REELS")
            elif re.search(r"\bemail", first_answer):
                SYSTEM_PROMPT = EMAIL_SYSTEM_PROMPT
                print("✅ Selected SYSTEM_PROMPT: EMAIL")
            elif re.search(r"\b(carousel|carousal)", first_answer):
                SYSTEM_PROMPT = CAROUSEL_SYSTEM_PROMPT
                print("✅ Selected SYSTEM_PROMPT: CAROUSEL")
            else:
                SYSTEM_PROMPT = GENERIC_SYSTEM_PROMPT
                print("✅ Selected SYSTEM_PROMPT: GENERIC")
        else:
            SYSTEM_PROMPT = GENERIC_SYSTEM_PROMPT
            print("✅ Selected SYSTEM_PROMPT: GENERIC (no previous context)")
        
        ChatMessage.objects.create(
            thread=thread, sender="user",
            message=prompt
        )
        
        # ✅ Load full history from database
        messages = thread.messages.order_by('timestamp')  # thanks to related_name="messages"

        conversation_history = ""
        for msg in messages:
            role = "User" if msg.sender == "user" else "AI"
            conversation_history += f"{role}: {msg.message}\n"

        # ✅ Emphasize main query
        conversation_history += (
            "\nNow here is the main question the user wants you to answer. "
            "Please generate your response considering the previous context:\n"
        )
        conversation_history += f"User: {prompt}\nAI:"

        # ✅ Call AI
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": conversation_history}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        ai_response = clean_response(response.choices[0].message.content)
        cleaned_ai_response = clean_ai_text(ai_response)

        # Save AI message
        ChatMessage.objects.create(
            thread=thread,
            sender="ai",
            message=cleaned_ai_response
        )

        return Response({
            "thread_id": thread.thread_id,
            "response": cleaned_ai_response,
            "prompt": prompt,
            "error": None
        })


class UpdateThreadTitleView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        data = request.data
        thread_id = data.get('thread_id', '').strip()
        new_title = data.get('title', '').strip()

        if not thread_id or not new_title:
            return Response(
                {'error': 'thread_id and title are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            thread = ChatThread.objects.get(user=request.user, thread_id=thread_id)
            thread.title = new_title
            thread.save()
            return Response({
                'thread_id': thread.thread_id,
                'title': thread.title,
                'updated_at': thread.created_at  # or timezone.now() if you add modified
            })
        except ChatThread.DoesNotExist:
            return Response(
                {'error': 'Thread not found'},
                status=status.HTTP_404_NOT_FOUND
            )