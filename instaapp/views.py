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

   

class onBoardingAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        answers = request.data.get('answers', [])
        if not answers:
            return Response({"error": "Answers are required."}, status=status.HTTP_400_BAD_REQUEST)

        ai_response_obj = onBoardingAnswer.objects.filter(
            user=request.user,
            question="onBoardingAiResponse"
        ).first()

        if ai_response_obj:
            return Response({
                "message": "AI response already exists.",
                "ai_response": ai_response_obj.answer
            }, status=status.HTTP_200_OK)

        # Save or update each answer
        for item in answers:
            question_text = item.get('question')
            answer_text = item.get('answer')

            if not question_text or not answer_text:
                continue  # Skip invalid entries

            onBoardingAnswer.objects.update_or_create(
                user=request.user,
                question=question_text,
                defaults={'answer': answer_text}
            )

        # Retrieve all user answers
        user_answers_qs = onBoardingAnswer.objects.filter(user=request.user)

        if not user_answers_qs.exists():
            return Response({"error": "No onboarding data found for the user."}, status=status.HTTP_400_BAD_REQUEST)

        # Build user persona and get AI response
        try:
            user_persona = build_user_persona(user_answers_qs)
            initial_prompt = (
                "Based on the following user persona, generate a warm, friendly personalized summary "
                "that welcomes them and suggests how you can assist going forward:\n\n"
                f"{user_persona}"
            )

            ai_response = create_chat_completion(user_persona, initial_prompt)

            onBoardingAnswer.objects.update_or_create(
                user=request.user,
                question="onBoardingAiResponse",
                defaults={'answer': ai_response}
            )
        except Exception as e:
            return Response({"error": f"Error generating AI response: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "Answers submitted successfully."}, status=status.HTTP_200_OK)   

    def get(self, request):
        ai_response_obj = onBoardingAnswer.objects.filter(
            user=request.user,
            question="onBoardingAiResponse"
        ).first()

        if ai_response_obj:
            return Response({
                "ai_response": ai_response_obj.answer
            }, status=status.HTTP_200_OK)

        return Response({
            "error": "No onboarding AI response found for this user."
        }, status=status.HTTP_404_NOT_FOUND)

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


def build_user_persona(user_answers):
    # Convert queryset of models to dict
    answers = {qa.question.lower(): qa.answer for qa in user_answers}
    
    # Same as before...
    first_name = answers.get("what's your first name?", "Unknown")
    help_statement = answers.get("in one sentence, what do you help people do?", "Not specified")
    brand_name = answers.get("what is your brand or business name?", "Unnamed brand")
    primary_goal = answers.get("what do you want help with most?", "Various things")
    tone_tags = answers.get("voice tone", "Neutral").split(",")
    tone = ", ".join([t.strip() for t in tone_tags])

    intro = (
        f"You are chatting with {first_name}, who runs a brand called \"{brand_name}\".\n"
        f"They help people with this: \"{help_statement}\".\n"
        f"Their goals include: {primary_goal}.\n"
        f"They want content that sounds {tone.lower()}.\n"
        f"They prefer medium to long content by default.\n"
        f"Always respond in a tone that reflects their personality and voice."
    )

    offers = answers.get("your offers")
    if offers and offers.strip():
        intro += f"\nHere are their offers:\n- {offers.strip()}"

    origin_story = answers.get("how did this all start? what pushed you to build your business?", "").strip()
    challenges = answers.get("what challenges have you overcome along the way?", "").strip()
    wins = answers.get("what's gone right? this is your moment!", "").strip()

    if origin_story:
        intro += f"\nTheir origin story: {origin_story}"
    if challenges:
        intro += f"\nChallenges they've overcome: {challenges}"
    if wins:
        intro += f"\nBig wins:\n- {wins}"

    return intro


def create_chat_completion(user_persona, user_input):
        messages = [
            {"role": "system", "content": f"""You are a creative, friendly AI assistant called 'DB'. 
        You help users generate content aligned with their brand and tone.
        {user_persona}
        """},
                {"role": "user", "content": user_input}
            ]
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages
        )
        return response.choices[0].message.content
    
class ContentChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        new_chat = data.get('new_chat', {})
        prompt = data.get('prompt', '').strip()
        thread_id = data.get('thread_id', '').strip()

        # ✅ Load user onboarding data (stored as JSON in DB)
        try:
            user_answers_qs = onBoardingAnswer.objects.filter(user=request.user)

            if not user_answers_qs.exists():
                return Response({"error": "No onboarding data found for user."}, status=status.HTTP_400_BAD_REQUEST)
        except AttributeError:
            return Response({"error": "No onboarding data found for user."}, status=status.HTTP_400_BAD_REQUEST)

        # Build user persona text
        user_persona = build_user_persona(user_answers_qs)

        # === If continuing conversation ===
        if not prompt:
            return Response({'error': 'prompt is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get or create chat thread
        if not thread_id:
            thread_id = str(uuid.uuid4())

        thread, created = ChatThread.objects.get_or_create(
            user=request.user,
            thread_id=thread_id,
            defaults={'title': prompt}
        )
        if created:
            print(f"New thread created with title from prompt: {prompt}")
        elif not thread.title or thread.title == "Personalized onboarding summary":
            thread.title = prompt
            thread.save()

        # Build conversation history
        conversation_history = ""
        if new_chat:
            conversation_history += "Context from previous exchanges:\n"
            for question, answer in new_chat.items():
                ChatMessage.objects.create(thread=thread, sender="ai", message=question)
                ChatMessage.objects.create(thread=thread, sender="user", message=answer)
                conversation_history += f"User: {question}\nAI: {answer}\n"

        # Load existing messages from DB
        messages = thread.messages.order_by('timestamp')
        for msg in messages:
            role = "User" if msg.sender == "user" else "AI"
            conversation_history += f"{role}: {msg.message}\n"

        # Append the current question
        conversation_history += f"\nNow the user asks: {prompt}\nAI:"

        # Call AI with persona + conversation
        full_prompt = (
            f"{user_persona}\n\n"
            "Here's the conversation so far:\n"
            f"{conversation_history}"
        )

        ai_response = create_chat_completion(user_persona, full_prompt)

        ChatMessage.objects.create(thread=thread, sender="user", message=prompt)
        ChatMessage.objects.create(thread=thread, sender="ai", message=ai_response)

        return Response({
            "thread_id": thread.thread_id,
             "thread_title": thread.title,
            "response": ai_response,
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