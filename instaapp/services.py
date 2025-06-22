import requests
from bs4 import BeautifulSoup
import pytesseract
from PIL import Image
import io
import re
import logging
from openai import OpenAI
import json
from django.conf import settings
from .models import ConversationThread, Message
from django.db import connection

logger = logging.getLogger(__name__)

class InstagramScraper:
    def __init__(self):
        """Initialize InstagramScraper with session headers."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        logger.info("[InstagramScraper] Initialized InstagramScraper instance.")
        try:
            connection.ensure_connection()
            logger.info("[InstagramScraper] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[InstagramScraper] Database connection error: {db_exc}")

    def is_valid_instagram_url(self, url):
        """Validate Instagram URL format."""
        logger.debug(f"[InstagramScraper] Validating Instagram URL: {url}")
        instagram_pattern = r'https?://(www\.)?(instagram\.com|instagr\.am)/p/[A-Za-z0-9_-]+/?'
        return bool(re.match(instagram_pattern, url))

    def scrape_instagram_post(self, url):
        """Scrape Instagram post for caption and images."""
        logger.info(f"[InstagramScraper] Scraping Instagram post: {url}")
        try:
            connection.ensure_connection()
            logger.info("[InstagramScraper] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[InstagramScraper] Database connection error: {db_exc}")
        try:
            if not self.is_valid_instagram_url(url):
                logger.warning(f"[InstagramScraper] Invalid Instagram URL: {url}")
                raise ValueError("Invalid Instagram URL format")
            if not url.endswith('/'):
                logger.debug(f"[InstagramScraper] Appending '/' to URL: {url}")
                url += '/'
            embed_url = url + 'embed/'
            logger.debug(f"[InstagramScraper] Embed URL: {embed_url}")
            response = self.session.get(embed_url, timeout=10)
            logger.info(f"[InstagramScraper] HTTP status: {response.status_code}, body: {response.text}")
            response.raise_for_status()
            logger.info(f"[InstagramScraper] Fetched embed page for: {url}")
            soup = BeautifulSoup(response.content, 'html.parser')
            caption = ""
            caption_elements = soup.find_all(['p', 'div'], class_=re.compile(r'caption|text', re.I))
            for element in caption_elements:
                logger.debug(f"[InstagramScraper] Found caption element: {element}")
                text = element.get_text(strip=True)
                if len(text) > len(caption):
                    caption = text
            image_urls = []
            img_tags = soup.find_all('img')
            logger.debug(f"[InstagramScraper] Found {len(img_tags)} image tags.")
            for img in img_tags:
                src = img.get('src')
                if src and ('instagram' in src or 'cdninstagram' in src):
                    image_urls.append(src)
            image_urls = list(dict.fromkeys(image_urls))
            logger.info(f"[InstagramScraper] Scraped caption: {caption}, image_urls: {image_urls}")
            return {
                'caption': caption,
                'image_urls': image_urls[:10]
            }
        except Exception as e:
            logger.error(f"[InstagramScraper] Error scraping post: {e}")
            raise

    def download_and_ocr_image(self, image_url):
        """Download image and extract text using OCR."""
        logger.info(f"[InstagramScraper] Downloading and OCR for image: {image_url}")
        try:
            connection.ensure_connection()
            logger.info("[InstagramScraper] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[InstagramScraper] Database connection error: {db_exc}")
        try:
            response = self.session.get(image_url, timeout=10)
            logger.info(f"[InstagramScraper] HTTP status: {response.status_code}")
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            text = pytesseract.image_to_string(image)
            logger.info(f"[InstagramScraper] OCR text: {text}")
            return text.strip()
        except Exception as e:
            logger.error(f"[InstagramScraper] Error in OCR: {e}")
            return ""

class ContentGenerator:
    def __init__(self):
        """Initialize ContentGenerator with OpenAI client."""
        logger.info("[ContentGenerator] Initializing OpenAI client.")
        try:
            connection.ensure_connection()
            logger.info("[ContentGenerator] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ContentGenerator] Database connection error: {db_exc}")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.FINE_TUNED_MODEL_ID

    def get_conversation_context(self, thread_id, limit=10):
        """Get last N messages from conversation thread."""
        logger.info(f"[ContentGenerator] Getting conversation context for thread: {thread_id}")
        try:
            connection.ensure_connection()
            logger.info("[ContentGenerator] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ContentGenerator] Database connection error: {db_exc}")
        try:
            thread = ConversationThread.objects.get(id=thread_id)
            messages = Message.objects.filter(thread=thread).order_by('-timestamp')[:limit]
            context = []
            for msg in reversed(messages):
                logger.debug(f"[ContentGenerator] Message: {msg}")
                if msg.message_type == 'user':
                    context.append({
                        "role": "user",
                        "content": f"Description: {msg.content.get('description', '')}"
                    })
                elif msg.message_type == 'assistant':
                    slides = msg.content.get('carousel_content', {}).get('slides', {})
                    slides_text = "\n".join([f"Slide {k}: {v}" for k, v in slides.items()])
                    context.append({
                        "role": "assistant",
                        "content": slides_text
                    })
            logger.debug(f"[ContentGenerator] Conversation context: {context}")
            return context
        except ConversationThread.DoesNotExist:
            logger.warning(f"[ContentGenerator] ConversationThread not found: {thread_id}")
            return []

    def generate_carousel_content(self, content_type, description, slides, inspiration_text=None, thread_id=None):
        """Generate carousel content using fine-tuned OpenAI model with context."""
        logger.info(f"[ContentGenerator] Generating carousel content. content_type: {content_type}, slides: {slides}, thread_id: {thread_id}")
        user_prompt = f"""Create a {slides}-slide Instagram carousel with the following requirements:\n\nContent Type: {content_type}\nDescription: {description}\nNumber of Slides: {slides}"""
        if inspiration_text:
            logger.debug(f"[ContentGenerator] Using inspiration text: {inspiration_text}")
            user_prompt += f"\nInspiration Content: {inspiration_text}\n\nPlease use the inspiration content to enhance and inform your carousel creation, but focus primarily on the main description."
        user_prompt += f"\n\nPlease generate exactly {slides} slides following the structure:\n- Slide 1: Attention-grabbing hook\n- Slides 2-{slides-1}: Main content/story\n- Slide {slides}: Call to action\n\nReturn the response as a JSON object with this structure:\n{{\n  \"slides\": {{\n    \"1\": \"First slide content here...\",\n    \"2\": \"Second slide content here...\",\n    ...\n    \"{slides}\": \"Last slide content here...\"\n  }}\n}}"
        try:
            messages = []
            if thread_id:
                context = self.get_conversation_context(thread_id)
                messages.extend(context)
            messages.append({"role": "user", "content": user_prompt})
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4000,
                temperature=0.7
            )
            content = response.choices[0].message.content
            logger.info(f"[ContentGenerator] OpenAI response: {content}")
            try:
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.rfind("```")
                    content = content[json_start:json_end].strip()
                parsed_content = json.loads(content)
                logger.info(f"[ContentGenerator] Parsed content: {parsed_content}")
                return parsed_content
            except json.JSONDecodeError:
                logger.warning(f"[ContentGenerator] JSON decode error, returning raw content.")
                return {
                    "slides": {
                        str(i): f"Slide {i} content from fine-tuned model response"
                        for i in range(1, slides + 1)
                    },
                    "raw_content": content,
                    "model_used": self.model
                }
        except Exception as e:
            logger.error(f"[ContentGenerator] Error generating carousel content: {e}")
            raise

class ConversationService:
    def __init__(self):
        """Initialize ConversationService with scraper and generator."""
        logger.info("[ConversationService] Initializing ConversationService.")
        try:
            connection.ensure_connection()
            logger.info("[ConversationService] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")
        self.scraper = InstagramScraper()
        self.generator = ContentGenerator()

    def create_or_get_thread(self, thread_id=None):
        """Create new thread or get existing one."""
        logger.info(f"[ConversationService] create_or_get_thread called with thread_id: {thread_id}")
        try:
            connection.ensure_connection()
            logger.info("[ConversationService] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")
        if thread_id:
            try:
                return ConversationThread.objects.get(id=thread_id)
            except ConversationThread.DoesNotExist:
                pass
        return ConversationThread.objects.create()

    def save_message(self, thread, message_type, content):
        """Save message to thread."""
        logger.info(f"[ConversationService] Saving message. thread: {thread.id}, type: {message_type}, content: {content}")
        try:
            connection.ensure_connection()
            logger.info("[ConversationService] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")
        return Message.objects.create(
            thread=thread,
            message_type=message_type,
            content=content
        )

    def process_inspiration(self, inspiration):
        """Process inspiration: Instagram URL or email/text content."""
        logger.info(f"[ConversationService] Processing inspiration: {inspiration}")
        if not inspiration:
            logger.warning("[ConversationService] No inspiration provided.")
            return None
        if self.scraper.is_valid_instagram_url(inspiration):
            logger.info(f"[ConversationService] Inspiration is an Instagram URL: {inspiration}")
            try:
                scraped_data = self.scraper.scrape_instagram_post(inspiration)
                logger.info(f"[ConversationService] Scraped data: {scraped_data}")
                text_parts = []
                if scraped_data['caption']:
                    text_parts.append(f"Caption: {scraped_data['caption']}")
                for i, image_url in enumerate(scraped_data['image_urls']):
                    try:
                        ocr_text = self.scraper.download_and_ocr_image(image_url)
                        if ocr_text:
                            text_parts.append(f"Image {i+1} text: {ocr_text}")
                    except Exception as e:
                        logger.warning(f"Failed to process image {i+1}: {str(e)}")
                        continue
                result = "\n\n".join(text_parts) if text_parts else None
                logger.info(f"[ConversationService] Inspiration processed result: {result}")
                return result
            except Exception as e:
                logger.error(f"Error processing Instagram URL: {str(e)}")
                return None
        else:
            logger.info(f"[ConversationService] Inspiration is treated as email/text content.")
            return inspiration

    def generate_carousel(self, description, content_type, slides=5, inspiration=None, thread_id=None):
        """Main method to generate carousel content."""
        logger.info(f"[ConversationService] generate_carousel called. description: {description}, content_type: {content_type}, slides: {slides}, inspiration: {inspiration}, thread_id: {thread_id}")
        try:
            connection.ensure_connection()
            logger.info("[ConversationService] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")
        thread = self.create_or_get_thread(thread_id)
        inspiration_text = self.process_inspiration(inspiration)
        user_content = {
            'description': description,
            'content_type': content_type,
            'slides': slides,
            'inspiration': inspiration
        }
        self.save_message(thread, 'user', user_content)
        carousel_content = self.generator.generate_carousel_content(
            content_type=content_type,
            description=description,
            slides=slides,
            inspiration_text=inspiration_text,
            thread_id=thread.id
        )
        assistant_content = {
            'carousel_content': carousel_content,
            'model_used': self.generator.model
        }
        self.save_message(thread, 'assistant', assistant_content)
        logger.info(f"[ConversationService] Carousel content generated and saved. Thread: {thread.id}, Response: {carousel_content}")
        return {
            'thread_id': str(thread.id),
            'carousel_content': carousel_content,
            'inspiration_processed': bool(inspiration_text),
            'model_used': self.generator.model
        }