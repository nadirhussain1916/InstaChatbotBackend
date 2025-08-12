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
from instaapp.models import Instagram_User, InstagramPost,onBoardingAnswer,ChatThread, ChatMessage,SystemPrompt
from .serializers import InstagramUserSerializer, InstagramPostSerializer, CarouselGeneratorSerializer,ChatThreadSerializer,ChatSerializer,SystemPromptSerializer
from instaapp.helper import save_user_profile, fetch_user_instagram_profile_data, check_instagram_credentials, get_and_save_post_detail,fetch_user_instagram_profile_data_byInstaloader,get_and_save_post_detail_byplaywright
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
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status,permissions

from .models import onBoardingAnswer

import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract


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

class CustomSignUpView(APIView):
    http_method_names = ['post']

    def post(self, request):
        """Handle user sign-up and authentication."""
        logger.info(f"[CustomSignUpView] POST request received. Data: {request.data}")
        logger.info(f"[CustomSignUpView] Checking database connection...")
        try:
            connection.ensure_connection()
            logger.info("[CustomSignUpView] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[CustomSignUpView] Database connection error: {db_exc}")
            return Response({'error': 'Database connection error.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        username = request.data.get('username')
        password = request.data.get('password')

        logger.info(f"[CustomSignUpView] Params - username: {username}")

        if not username or not password:
            logger.warning("[CustomSignUpView] Username or password missing.")
            return Response({'error': 'Username and password required.'}, status=status.HTTP_400_BAD_REQUEST)

        if '@' in username:
            logger.warning("[CustomSignUpView] Email provided instead of username.")
            return Response({'error': 'Please enter your Instagram username, not email.'}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Check if username already exists
        if User.objects.filter(username=username).exists():
            logger.warning("[CustomSignUpView] Username already exists.")
            return Response({'error': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            logger.info(f"[InstagramFetchData] Fetching Instagram profile data for: {username}")
            res = fetch_user_instagram_profile_data(username)
            logger.info(f"[InstagramFetchData] Response: {res}")
            print('=-=-=-=-res=-=-=-=-',res)
            if res:
                business_discovery_res = res.get("business_discovery")
                if business_discovery_res:
                    user = User.objects.create_user(username=username, password=password)
                    if user:
                        Instagram_User.objects.create(
                            user=user,
                            username=username,
                            password=encrypt_password(password),
                            is_insta_api=False
                        )

                        user = authenticate(username=username, password=password)
                    
                        refresh = RefreshToken.for_user(user)
                        
                        save_user_profile(
                        username,
                        business_discovery_res.get("name"),
                        business_discovery_res.get("followers_count"),
                        business_discovery_res.get("media_count"),
                        business_discovery_res.get("profile_picture_url"),
                    )
                        logger.info(f"[InstagramFetchData] Instagram data fetched and saved for: {username}")

                    
                        response_data = {
                        "status": "success",
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                        "has_answered": False
                    }
                        logger.info(f"[CustomSignUpView] Response: {response_data}")
                        return Response(response_data, status=status.HTTP_201_CREATED)
                    else:
                        logger.error(f"[CustomSignUpView] Authentication failed after user creation for '{username}'.")
                        return Response({
                            "status": "error",
                            "message": "Authentication failed after user creation."
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                else:
                    logger.warning(f"[InstagramFetchData] 'business_discovery' not found in response for: {username}")
                    return Response({
                        "status": "error",
                        "message": "Instagram profile data not available."
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                result = fetch_user_instagram_profile_data_byInstaloader(username)
                if result:
                    user = User.objects.create_user(username=username, password=password)
                    if user:
                        print('----------12123')
                        Instagram_User.objects.create(
                            user=user,
                            username=username,
                            password=encrypt_password(password),
                            is_insta_api = True
                        )

                        user = authenticate(username=username, password=password)
                    
                        refresh = RefreshToken.for_user(user)
                        
                        save_user_profile(
                        username,
                        result.get("name"),
                        result.get("followers_count"),
                        result.get("media_count"),
                        result.get("profile_picture_url"),
                    )
                        logger.info(f"[InstagramFetchData] Instagram data fetched and saved for: {username}")

                    
                        response_data = {
                        "status": "success",
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                        "has_answered": False
                    }
                        logger.info(f"[CustomSignUpView] Response: {response_data}")
                        return Response(response_data, status=status.HTTP_201_CREATED)

                else:
                    logger.error(f"[InstagramFetchData] Failed to fetch Instagram profile data for: {username}")
                    return Response({
                        "status": "error",
                        "message": "Instagram profile data fetch failed. Please check server configuration."
                    }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"[CustomSignUpView] Exception during sign-up: {str(e)}")
            return Response(
                {"error": f"Failed to complete sign-up: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )    
        
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
                # Determine role from built-in is_staff
            role = "admin" if user.is_staff else "user"

            response_data = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'has_answered':has_answered,
                "role":role
            }
            logger.info(f"[CustomSignInView] Response: {response_data}")
            return Response(response_data)
        else:
            logger.info(f"[CustomSignInView] User '{username}' not found or wrong password. Checking Instagram credentials.")
            return Response({"status": "error",
                            "message": "Authentication failed. Please check your username and password."
                        }, status=status.HTTP_400_BAD_REQUEST)
            
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
                    if insta_user.is_insta_api:
                        res = fetch_user_instagram_profile_data_byInstaloader(insta_username)
                    else:   
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
                if insta_user.is_insta_api:
                    get_and_save_post_detail_byplaywright(insta_username)
                else:
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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    """Return the profile of the authenticated Instagram user."""
    logger.info(f"[get_user_profile] GET request by user: {request.user.username}")
    
    auth_username = request.user.username
    role = "admin" if request.user.is_staff else "user"  # use request.user.is_staff directly
    user = get_object_or_404(Instagram_User, username=auth_username)
    serializer = InstagramUserSerializer(user)
    response_data = serializer.data
    response_data["role"] = role  # add role to the response
    logger.info(f"[get_user_profile] Profile data returned for user: {auth_username}. Response: {serializer.data}")
    return Response(response_data)

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
        # Extract and parse answers
        raw_answers = request.data.get("answers", "[]")
        try:
            answers = json.loads(raw_answers)
        except json.JSONDecodeError:
            return Response({"error": "Invalid JSON format for answers."}, status=400)

        # Handle uploaded file (optional)
        uploaded_file = request.FILES.get("file")
        extracted_text = ""

        if uploaded_file:
            content_type = uploaded_file.content_type
            print("Uploaded Content-Type:", uploaded_file.content_type)
            try:
                if content_type == "application/pdf":
                    extracted_text = self.extract_text_from_pdf(uploaded_file)
                elif content_type in [
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/msword"
                ]:
                    extracted_text = self.extract_text_from_doc(uploaded_file)
                elif content_type.startswith("image/"):
                    extracted_text = self.extract_text_from_image(uploaded_file)
                elif content_type == "text/plain":
                    extracted_text = uploaded_file.read().decode("utf-8")
                    print("Extracted text from plain file:", extracted_text)
                else:
                    return Response({"error": "Unsupported file type."}, status=400)

                # Save extracted content as a special answer
                onBoardingAnswer.objects.update_or_create(
                    user=request.user,
                    question="file_upload_content",
                    defaults={'answer': extracted_text}
                )

            except Exception as e:
                return Response({"error": f"File processing error: {str(e)}"}, status=500)

        # Skip if no manual answers and no file
        if not answers and not extracted_text:
            return Response({"error": "Answers or file are required."}, status=400)

        # Prevent duplicate AI response
        ai_response_obj = onBoardingAnswer.objects.filter(
            user=request.user,
            question="onBoardingAiResponse"
        ).first()
        if ai_response_obj:
            return Response({
                "message": "AI response already exists.",
                "ai_response": ai_response_obj.answer
            }, status=200)

        # Save text-based answers
        for item in answers:
            question_text = item.get('question')
            answer_text = item.get('answer')
            if not question_text or not answer_text:
                continue
            onBoardingAnswer.objects.update_or_create(
                user=request.user,
                question=question_text,
                defaults={'answer': answer_text}
            )

        # Get all user answers
        user_answers_qs = onBoardingAnswer.objects.filter(user=request.user)
        if not user_answers_qs.exists():
            return Response({"error": "No onboarding data found for the user."}, status=400)

        # Generate AI response
        try:
            user_persona = build_user_persona(user_answers_qs)
            prompt = (
                "Based on the following user persona, write a short and warm welcome message in 3 to 5 lines. "
                "Keep it friendly, personalized, and clearly mention how you can help going forward:\n\n"
                f"{user_persona}"
            )
            ai_response = create_chat_completion(user_persona, prompt)
            onBoardingAnswer.objects.update_or_create(
                user=request.user,
                question="onBoardingAiResponse",
                defaults={'answer': ai_response}
            )
        except Exception as e:
            return Response({"error": f"AI generation failed: {str(e)}"}, status=500)

        return Response({"message": "Answers submitted successfully."}, status=200)

    # Text extractors
    def extract_text_from_pdf(self, file):
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file.read(), filetype="pdf")
        return "\n".join(page.get_text() for page in doc)

    def extract_text_from_doc(self, file):
        from docx import Document
        return "\n".join(para.text for para in Document(file).paragraphs)

    def extract_text_from_image(self, file):
        """Extract text from a local image file using OCR."""
        from PIL import Image
        import pytesseract
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.info(f"[InstagramScraper] Processing local image for OCR: {file}")
            image = Image.open(file)

            if image.mode != 'RGB':
                logger.info(f"[InstagramScraper] Converting image from {image.mode} to RGB")
                image = image.convert('RGB')

            logger.info("[InstagramScraper] Running OCR on local image...")
            text = pytesseract.image_to_string(image)
            extracted_text = text.strip()

            if extracted_text:
                logger.info(f"[InstagramScraper] OCR successful - extracted {len(extracted_text)} characters")
                logger.info(f"[InstagramScraper] OCR text preview: {extracted_text[:100]}..." if len(extracted_text) > 100 else f"[InstagramScraper] OCR text: {extracted_text}")
            else:
                logger.info("[InstagramScraper] OCR completed but no text found in image")

            return extracted_text

        except Exception as e:
            logger.error(f"[InstagramScraper] Error during OCR on local file: {str(e)}", exc_info=True)
            return ""

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

class ChatThreadCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return a new unique thread_id without creating it in DB"""
        thread_id = str(uuid.uuid4())
        return Response({'new_chat_id': thread_id}, status=status.HTTP_200_OK)


def build_user_persona(user_answers):
    # Convert queryset of models to dict
    answers = {qa.question.lower(): qa.answer for qa in user_answers}
    print("User answers:", answers)
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
    
        # ✅ Add extracted text if available
    file_input = answers.get("file_upload_content", "").strip()
    if file_input:
        intro += f"\n\nAdditional input from uploaded file:\n{file_input}"

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
            if msg.sender == "user" and msg.message in ["Carousel", "Reel", "Email"]:
                system_prompt_name = msg.message
            role = "User" if msg.sender == "user" else "AI"
            conversation_history += f"{role}: {msg.message}\n"
            
        if system_prompt_name == "Carousel":
            system_prompt = "CAROUSEL_SYSTEM_PROMPT"  
        elif system_prompt_name == "Reel":
            system_prompt = "REELS_SYSTEM_PROMPT"
        elif system_prompt_name == "Email":
            system_prompt = "EMAIL_SYSTEM_PROMPT"
        else:
            system_prompt = "GENERIC_SYSTEM_PROMPT"           
            
        # Append the current question
        conversation_history += f"\nNow the user asks: {prompt}\nAI:"
        system_prompt = get_active_system_prompt(name=system_prompt)  # or "default" if general
        
        # Add formatting instructions for Carousel only
        if system_prompt_name == "Carousel":
            system_prompt += (
                "\n\nFormat each slide like this:\n"
                "Slide 1: [Short title or idea]. [One or two complete, engaging sentences.]\n"
                "Avoid using markdown (** or -). Don't use bullet points."
            )
            
        full_prompt = (
            f"{system_prompt}\n\n"
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


def get_active_system_prompt(name="default"):
    try:
        return SystemPrompt.objects.get(name=name, is_active=True).content
    except SystemPrompt.DoesNotExist:
        return "You are a helpful assistant."  # fallback

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        
        if not current_password or not new_password:
            return Response({'error': 'new_password and current_password required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(current_password):
            return Response({'error': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)

class ResetPasswordView(APIView):
    def post(self, request):
        username = request.data.get('username')
        new_password = request.data.get('password')
        if not username or not new_password:
            return Response({'error': 'Username and new password are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(username=username)
            user.set_password(new_password)
            user.save()
            return Response({'message': 'Password reset successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User does not exist'}, status=status.HTTP_404_NOT_FOUND)
        

# Custom admin-only permission
class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)

class SystemPromptView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk=None):
        if pk:
            prompt = get_object_or_404(SystemPrompt, pk=pk)
            serializer = SystemPromptSerializer(prompt)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            prompts = SystemPrompt.objects.all()
            serializer = SystemPromptSerializer(prompts, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)


    def post(self, request):
        serializer = SystemPromptSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Prompt ID (pk) is required."}, status=status.HTTP_400_BAD_REQUEST)

        prompt = get_object_or_404(SystemPrompt, pk=pk)
        serializer = SystemPromptSerializer(prompt, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Prompt ID (pk) is required."}, status=status.HTTP_400_BAD_REQUEST)

        prompt = get_object_or_404(SystemPrompt, pk=pk)
        prompt.delete()
        return Response({"message": "Prompt deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
