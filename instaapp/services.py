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
import instaloader

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

    def is_valid_instagram_url(self, url: str) -> bool:
        """Check if the provided URL is a valid Instagram post URL."""
        pattern = r'^https?://(www\.)?instagram\.com/p/[A-Za-z0-9_\-]+/?(\?.*)?$'
        is_valid = re.match(pattern, url) is not None
        logger.info(f"[InstagramScraper] URL validation for '{url}': {is_valid}")
        return is_valid

    def extract_shortcode(self, url: str) -> str:
        """Extract the shortcode from the Instagram post URL."""
        logger.info(f"[InstagramScraper] Extracting shortcode from URL: {url}")
        match = re.search(r'/p/([A-Za-z0-9_\-]+)/?', url)
        if match:
            shortcode = match.group(1)
            logger.info(f"[InstagramScraper] Extracted shortcode: {shortcode}")
            return shortcode
        logger.error(f"[InstagramScraper] Could not extract shortcode from URL: {url}")
        raise ValueError("Could not extract shortcode from URL")

    def scrape_instagram_post(self, url: str):
        """Scrape Instagram post using Instaloader for caption and image URLs."""
        logger.info(f"[InstagramScraper] Starting to scrape Instagram post: {url}")
        try:
            if not self.is_valid_instagram_url(url):
                logger.warning(f"[InstagramScraper] Invalid Instagram URL format: {url}")
                raise ValueError("Invalid Instagram URL format")

            shortcode = self.extract_shortcode(url)
            logger.info(f"[InstagramScraper] Using shortcode: {shortcode}")

            logger.info("[InstagramScraper] Initializing Instaloader...")
            loader = instaloader.Instaloader()
            
            logger.info(f"[InstagramScraper] Fetching post data for shortcode: {shortcode}")
            post = instaloader.Post.from_shortcode(loader.context, shortcode)

            caption = post.caption or ""
            image_urls = []

            logger.info(f"[InstagramScraper] Post type: {post.typename}")
            logger.info(f"[InstagramScraper] Caption extracted: {caption[:100]}..." if len(caption) > 100 else f"[InstagramScraper] Caption extracted: {caption}")

            if post.typename == "GraphSidecar":
                logger.info("[InstagramScraper] Processing carousel post - extracting multiple images")
                for i, node in enumerate(post.get_sidecar_nodes()):
                    image_urls.append(node.display_url)
                    logger.info(f"[InstagramScraper] Added image {i+1} URL: {node.display_url}")
            else:
                logger.info("[InstagramScraper] Processing single image post")
                image_urls.append(post.url)
                logger.info(f"[InstagramScraper] Added single image URL: {post.url}")

            logger.info(f"[InstagramScraper] Total images found: {len(image_urls)}")
            
            # Limit to first 10 images to prevent excessive processing
            limited_image_urls = image_urls[:10]
            if len(image_urls) > 10:
                logger.info(f"[InstagramScraper] Limiting to first 10 images (original count: {len(image_urls)})")

            result = {
                'caption': caption,
                'image_urls': limited_image_urls
            }
            
            logger.info(f"[InstagramScraper] Successfully scraped post data")
            logger.info(f"[InstagramScraper] Final result - Caption length: {len(caption)}, Image URLs: {len(limited_image_urls)}")
            
            return result

        except Exception as e:
            logger.error(f"[InstagramScraper] Error scraping post: {str(e)}", exc_info=True)
            raise

    def download_and_ocr_image(self, image_url):
        """Download image and extract text using OCR."""
        logger.info(f"[InstagramScraper] Starting OCR process for image: {image_url}")
        try:
            connection.ensure_connection()
            logger.debug("[InstagramScraper] Database connection verified for OCR process.")
        except Exception as db_exc:
            logger.error(f"[InstagramScraper] Database connection error during OCR: {db_exc}")
        
        try:
            logger.info(f"[InstagramScraper] Downloading image from: {image_url}")
            response = self.session.get(image_url, timeout=10)
            logger.info(f"[InstagramScraper] Image download HTTP status: {response.status_code}")
            response.raise_for_status()
            
            logger.info("[InstagramScraper] Processing image for OCR...")
            image = Image.open(io.BytesIO(response.content))
            
            if image.mode != 'RGB':
                logger.info(f"[InstagramScraper] Converting image from {image.mode} to RGB")
                image = image.convert('RGB')
            
            logger.info("[InstagramScraper] Running OCR on image...")
            text = pytesseract.image_to_string(image)
            extracted_text = text.strip()
            
            if extracted_text:
                logger.info(f"[InstagramScraper] OCR successful - extracted {len(extracted_text)} characters")
                logger.info(f"[InstagramScraper] OCR text preview: {extracted_text[:100]}..." if len(extracted_text) > 100 else f"[InstagramScraper] OCR text: {extracted_text}")
            else:
                logger.info("[InstagramScraper] OCR completed but no text found in image")
            
            return extracted_text
            
        except Exception as e:
            logger.error(f"[InstagramScraper] Error in OCR process: {str(e)}", exc_info=True)
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
        logger.info(f"[ContentGenerator] Using model: {self.model}")

    def get_conversation_context(self, thread_id, limit=10):
        """Get last N messages from conversation thread."""
        logger.info(f"[ContentGenerator] Getting conversation context for thread: {thread_id}, limit: {limit}")
        try:
            connection.ensure_connection()
            logger.debug("[ContentGenerator] Database connection verified for context retrieval.")
        except Exception as db_exc:
            logger.error(f"[ContentGenerator] Database connection error: {db_exc}")
        
        try:
            thread = ConversationThread.objects.get(id=thread_id)
            messages = Message.objects.filter(thread=thread).order_by('-timestamp')[:limit]
            context = []
            
            logger.info(f"[ContentGenerator] Found {len(messages)} messages in thread")
            
            for i, msg in enumerate(reversed(messages)):
                logger.debug(f"[ContentGenerator] Processing message {i+1}: type={msg.message_type}, timestamp={msg.timestamp}")
                
                if msg.message_type == 'user':
                    context.append({
                        "role": "user",
                        "content": f"Description: {msg.content.get('description', '')}"
                    })
                elif msg.message_type == 'assistant':
                    slides = msg.content.get('carousel_content', {}).get('slides', {})
                    slides_text = slides
                    context.append({
                        "role": "assistant",
                        "content": slides_text
                    })
            
            logger.info(f"[ContentGenerator] Prepared context with {len(context)} messages")
            return context
            
        except ConversationThread.DoesNotExist:
            logger.warning(f"[ContentGenerator] ConversationThread not found: {thread_id}")
            return []

    def process_inspiration_with_openai(self, inspiration_text):
        """Process and reformat inspiration text using OpenAI."""
        logger.info("[ContentGenerator] Processing inspiration text with OpenAI for reformatting")
        
        if not inspiration_text or not inspiration_text.strip():
            logger.info("[ContentGenerator] No inspiration text to process")
            return inspiration_text
        
        try:
            reformat_prompt = f"""
Please analyze and reformat the following Instagram content for use as inspiration in creating new carousel content. 
Extract the key themes, messaging style, and valuable insights that could inspire new content creation.

Original Content:
{inspiration_text}

Please provide:
1. Key themes and topics
2. Messaging style and tone
3. Content structure insights
4. Actionable inspiration points

Format your response as clear, structured insights that can be used to inspire new carousel content creation.
"""
            
            logger.info("[ContentGenerator] Sending inspiration text to OpenAI for processing")
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Using standard model for processing
                messages=[
                    {"role": "system", "content": "You are an expert content analyst who specializes in extracting insights from social media content to inspire new content creation."},
                    {"role": "user", "content": reformat_prompt}
                ],
                max_tokens=1000,
                temperature=0.5
            )
            
            processed_inspiration = response.choices[0].message.content.strip()
            logger.info(f"[ContentGenerator] Successfully processed inspiration text - output length: {len(processed_inspiration)}")
            logger.info(f"[ContentGenerator] Processed inspiration preview: {processed_inspiration[:200]}...")
            
            return processed_inspiration
            
        except Exception as e:
            logger.error(f"[ContentGenerator] Error processing inspiration with OpenAI: {str(e)}", exc_info=True)
            logger.info("[ContentGenerator] Falling back to original inspiration text")
            return inspiration_text

    def generate_carousel_content(self, description,thread_id=None):
        """Generate carousel content using fine-tuned OpenAI model with context."""
        logger.info(f"[ContentGenerator] Starting carousel generation")
        logger.info(f"[ContentGenerator] Parameters - content_type: thread_id: {thread_id}")
        logger.info(f"[ContentGenerator] Description: {description}")
        

        try:
            messages = []
            
            # Add conversation context if thread_id provided
            if thread_id:
                logger.info(f"[ContentGenerator] Adding conversation context for thread: {thread_id}")
                context = self.get_conversation_context(thread_id)
                clean_context = []
                for msg in context:
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        content = "\n".join(content)
                    clean_context.append({
                        "role": msg.get("role"),
                        "content": content
                    })
                messages.extend(clean_context)
                logger.info(f"[ContentGenerator] Added {len(context)} context messages")
            
            messages.append({"role": "user", "content": description})
            
            logger.info(f"[ContentGenerator] Sending request to OpenAI with {len(messages)} messages")
            logger.info(f"[ContentGenerator] Using model: {self.model}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4000,
                temperature=0.7
            )
            
            content = response.choices[0].message.content
            logger.info(f"[ContentGenerator] Received OpenAI response - length: {len(content)}")
            
            try:
                # Parse JSON response
                logger.info("[ContentGenerator] Parsing JSON response...")
                
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.rfind("```")
                    content = content[json_start:json_end].strip()
                
                parsed_content = json.loads(content)
                logger.info(f"[ContentGenerator] Successfully parsed JSON response")
                logger.info(f"[ContentGenerator] Generated {len(parsed_content.get('slides', {}))} slides")
                
                return parsed_content
                
            except json.JSONDecodeError as e:
                logger.warning(f"[ContentGenerator] JSON decode error: {str(e)}")
                logger.info("[ContentGenerator] Attempting to create fallback slides structure")
                
                # Fallback: create basic slides structure
                content_lines = content.split('\n')
                
                
                fallback_content = {"slides": content_lines}
                logger.info(f"[ContentGenerator] Created fallback content with {len(fallback_content['slides'])} slides")
                return fallback_content
                
        except Exception as e:
            logger.error(f"[ContentGenerator] Error generating carousel content: {str(e)}", exc_info=True)
            raise


class ConversationService:
    def __init__(self):
        """Initialize ConversationService with scraper and content generator."""
        logger.info("[ConversationService] Initializing ConversationService")
        self.scraper = InstagramScraper()
        self.content_generator = ContentGenerator()
        try:
            connection.ensure_connection()
            logger.info("[ConversationService] Database connection OK.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")

    def get_or_create_thread(self, thread_id=None):
        """Get existing thread or create new one."""
        logger.info(f"[ConversationService] Getting or creating thread: {thread_id}")
        try:
            connection.ensure_connection()
            logger.debug("[ConversationService] Database connection verified for thread operations.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")
        
        try:
            if thread_id:
                logger.info(f"[ConversationService] Looking for existing thread: {thread_id}")
                thread = ConversationThread.objects.get(id=thread_id)
                logger.info(f"[ConversationService] Found existing thread: {thread_id}")
                return thread
        except ConversationThread.DoesNotExist:
            logger.info(f"[ConversationService] Thread {thread_id} not found, creating new thread")
        
        # Create new thread
        thread = ConversationThread.objects.create()
        logger.info(f"[ConversationService] Created new thread: {thread.id}")
        return thread

    def save_message(self, thread, message_type, content):
        """Save message to conversation thread."""
        logger.info(f"[ConversationService] Saving message to thread {thread.id}: type={message_type}")
        try:
            connection.ensure_connection()
            logger.debug("[ConversationService] Database connection verified for message saving.")
        except Exception as db_exc:
            logger.error(f"[ConversationService] Database connection error: {db_exc}")
        
        try:
            message = Message.objects.create(
                thread=thread,
                message_type=message_type,
                content=content
            )
            logger.info(f"[ConversationService] Saved message {message.id} to thread {thread.id}")
            return message
        except Exception as e:
            logger.error(f"[ConversationService] Error saving message: {str(e)}", exc_info=True)
            raise

    def process_inspiration(self, inspiration):
        """Process inspiration content (Instagram URL or text)."""
        logger.info(f"[ConversationService] Processing inspiration content")
        
        if not inspiration or not inspiration.strip():
            logger.info("[ConversationService] No inspiration content provided")
            return None
        
        try:
            # Check if it's an Instagram URL
            if self.scraper.is_valid_instagram_url(inspiration):
                logger.info("[ConversationService] Processing Instagram URL inspiration")
                
                # Scrape Instagram post
                scraped_data = self.scraper.scrape_instagram_post(inspiration)
                caption = scraped_data.get('caption', '')
                image_urls = scraped_data.get('image_urls', [])
                
                logger.info(f"[ConversationService] Scraped data - Caption: {len(caption)} chars, Images: {len(image_urls)}")
                
                # Extract text from images using OCR
                ocr_texts = []
                for i, image_url in enumerate(image_urls[:5]):  # Limit to first 5 images
                    logger.info(f"[ConversationService] Processing image {i+1}/{min(len(image_urls), 5)} for OCR")
                    ocr_text = self.scraper.download_and_ocr_image(image_url)
                    if ocr_text:
                        ocr_texts.append(ocr_text)
                
                # Combine caption and OCR texts
                combined_text = caption
                if ocr_texts:
                    combined_text += "\n\nExtracted text from images:\n" + "\n".join(ocr_texts)
                
                logger.info(f"[ConversationService] Combined inspiration text length: {len(combined_text)}")
                return combined_text
            
            else:
                logger.info("[ConversationService] Processing text/email inspiration")
                return inspiration.strip()
                
        except Exception as e:
            logger.error(f"[ConversationService] Error processing inspiration: {str(e)}", exc_info=True)
            logger.info("[ConversationService] Falling back to original inspiration text")
            return inspiration.strip() if inspiration else None

    def generate_carousel(self, description, thread_id=None):
        """Generate carousel content with optional inspiration and conversation context."""
        logger.info("[ConversationService] Starting carousel generation process")
        logger.info(f"[ConversationService] Parameters - content_type: thread_id: {thread_id}")
        
        try:
            # Get or create conversation thread
            thread = self.get_or_create_thread(thread_id)
                       
            # Save user message
            user_message_content = {
                'description': description,
            }
            
            self.save_message(thread, 'user', user_message_content)
            
            # Generate carousel content
            logger.info("[ConversationService] Generating carousel content with ContentGenerator")
            carousel_content = self.content_generator.generate_carousel_content(
                description=description,
                thread_id=thread.id
            )
            
            # Save assistant response
            assistant_message_content = {
                'carousel_content': carousel_content,
                'model_used': self.content_generator.model,
            }
            
            self.save_message(thread, 'assistant', assistant_message_content)
            
            logger.info(f"[ConversationService] Carousel generation completed successfully")
            
            return {
                'thread_id': thread.id,
                'carousel_content': carousel_content,
                'model_used': self.content_generator.model,
            }
            
        except Exception as e:
            logger.error(f"[ConversationService] Error in carousel generation: {str(e)}", exc_info=True)
            raise
        

# In-memory thread store with conversation state
threads = {}
conversation_states = {}

SYSTEM_PROMPT = """
You are Daily Bread AI, a professional content creation assistant specializing in social media and email marketing. Your role is to help users create high-quality content and provide expert advice on content strategy.

Core Guidelines:
- Maintain a professional, knowledgeable tone without excessive friendliness
- Provide clear, actionable guidance and suggestions
- Generate well-structured, professional content
- Handle modifications, improvements, and follow-up requests efficiently
- Never use emojis or special characters in responses
- Format responses with proper line breaks and spacing for readability
- Be conversational but maintain expertise and authority

Content Expertise Areas:
- Social Media Content (Carousels, Reels, Posts)
- Email Marketing (Nurture, Sales, Follow-up sequences)
- Content Strategy and Planning
- Audience Engagement Tactics
- Copywriting and Messaging
- Content Optimization and Performance

When in conversation mode (after initial content creation):
- Answer questions about content strategy and best practices
- Provide suggestions for content improvements and variations
- Offer advice on content marketing tactics
- Help with content planning and scheduling
- Discuss audience engagement strategies
- Provide feedback on user's content ideas
- Suggest content optimizations based on goals

Content Creation Standards:
- Professional and well-formatted output
- Aligned with specified goals and target audience
- Structured with clear sections and proper spacing
- Free of emojis and excessive punctuation
- Ready for immediate implementation
- Include strategic recommendations when relevant

Always maintain focus on practical, actionable content creation and marketing advice.
"""

def clean_response(text):
    """Remove emojis and format response properly"""
    # Remove emojis and special characters
    emoji_pattern = re.compile("["
                              u"\U0001F600-\U0001F64F"  # emoticons
                              u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                              u"\U0001F680-\U0001F6FF"  # transport & map symbols
                              u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                              u"\U00002702-\U000027B0"
                              u"\U000024C2-\U0001F251"
                              "]+", flags=re.UNICODE)
    
    text = emoji_pattern.sub('', text)
    
    # Clean up excessive punctuation
    text = re.sub(r'[!]{2,}', '!', text)
    text = re.sub(r'[?]{2,}', '?', text)
    
    # Fix email formatting specifically
    # Add line breaks after email elements
    text = re.sub(r'(Subject:.*?)([A-Z][a-z])', r'\1\n\n\2', text)  # After subject line
    text = re.sub(r'(\[.*?\],?)([A-Z])', r'\1\n\n\2', text)  # After recipient name
    text = re.sub(r'(\.)([A-Z][a-z].*?:)', r'.\n\n\2', text)  # Before new sections
    text = re.sub(r'(\d+\..+?)([A-Z][a-z])', r'\1\n\n\2', text)  # After numbered lists
    text = re.sub(r'(Best regards,|Sincerely,|Thank you,)([A-Z])', r'\1\n\n\2', text)  # Before signature
    
    # Ensure proper paragraph spacing
    text = re.sub(r'\.([A-Z])', r'.\n\n\1', text)  # Add double line break after sentences starting new thoughts
    
    # Fix numbered lists formatting
    text = re.sub(r'(\d+\.)([A-Z])', r'\1 \2', text)  # Space after numbers
    text = re.sub(r'(\d+\..+?)(\d+\.)', r'\1\n\n\2', text)  # Line breaks between list items
    
    # Clean up excessive line breaks but maintain proper spacing
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    return text

def get_conversation_state(thread_id):
    return conversation_states.get(thread_id, {
        'step': 'initial', 
        'content_type': None, 
        'goal': None, 
        'data': {},
        'content_generated': False
    })

def update_conversation_state(thread_id, updates):
    if thread_id not in conversation_states:
        conversation_states[thread_id] = {
            'step': 'initial', 
            'content_type': None, 
            'goal': None, 
            'data': {},
            'content_generated': False
        }
    conversation_states[thread_id].update(updates)

def get_next_question(state, user_message):
    step = state['step']
    content_type = state['content_type']
    goal = state['goal']
    data = state['data']
    content_generated = state.get('content_generated', False)

    # Handle post-content generation interactions - smart conversation mode
    if content_generated or step in ['handle_modification', 'general_chat']:
        return {
            'message': user_message,  # Pass user message for AI processing
            'next_step': 'smart_conversation',
            'needs_ai_response': True,
            'conversation_mode': True
        }

    if step == 'initial':
        return {
            'message': "What type of content would you like to create today?",
            'options': ['Carousel', 'Reel', 'Email'],
            'next_step': 'content_type_selected'
        }

    elif step == 'content_type_selected':
        content_type = user_message.lower()
        if 'carousel' in content_type:
            return {
                'message': "What is your primary goal for this carousel post?",
                'options': [
                    'Awareness - Increase visibility and grow following', 
                    'Nurture - Build engagement and trust with audience', 
                    'Sales - Promote product or service directly'
                ],
                'next_step': 'carousel_goal_selected'
            }
        elif 'reel' in content_type:
            return {
                'message': "What is your primary objective for this reel?",
                'options': ['Awareness', 'Engagement', 'Sales'],
                'next_step': 'reel_goal_selected'
            }
        elif 'email' in content_type:
            return {
                'message': "What is the main purpose of this email?",
                'options': [
                    'Nurture - Build trust and warm up audience',
                    'Sales - Drive purchases or bookings',
                    'Follow-up - Post-freebie or post-purchase',
                    'Re-engagement - Win back inactive subscribers',
                    'Welcome - Introduce new subscribers',
                    'Other'
                ],
                'next_step': 'email_goal_selected'
            }

    elif step == 'carousel_goal_selected':
        goal = user_message.lower()
        if 'sales' in goal:
            return {
                'message': "What specific product or service are you promoting?",
                'next_step': 'carousel_product_info'
            }
        elif 'awareness' in goal:
            return {
                'message': "What specific action should viewers take after seeing your carousel?",
                'options': [
                    'Follow your account',
                    'Comment with a specific keyword',
                    'Send a direct message',
                    'Save the post for later',
                    'Join your email list',
                    'Visit your website'
                ],
                'next_step': 'carousel_cta_selected'
            }
        elif 'nurture' in goal:
            return {
                'message': "What topic will help build trust and engagement with your audience?",
                'next_step': 'carousel_topic_selected'
            }

    elif step == 'carousel_product_info':
        return {
            'message': "What is your target audience for this product/service?",
            'next_step': 'generate_content'
        }

    elif step == 'carousel_cta_selected':
        return {
            'message': "What topic or value will you provide in this awareness carousel?",
            'next_step': 'generate_content'
        }

    elif step == 'carousel_topic_selected':
        return {
            'message': "What action should engaged viewers take next?",
            'options': [
                'Comment for more information',
                'Download a free resource',
                'Join a waitlist',
                'Send a direct message',
                'Visit your website'
            ],
            'next_step': 'generate_content'
        }

    elif step == 'email_goal_selected':
        return {
            'message': "What specific topic will this email cover?",
            'options': [
                'New product or service launch',
                'Client success story or testimonial',
                'Personal story or behind-the-scenes',
                'Educational content or insights',
                'Addressing common objections',
                'Teasing upcoming content or offers',
                'Delivering promised free content',
                'Promoting a discovery call or consultation'
            ],
            'next_step': 'email_topic_selected'
        }

    elif step == 'email_topic_selected':
        return {
            'message': "What is the primary action you want readers to take?",
            'options': [
                'Click a specific link',
                'Reply to the email',
                'Send a direct message with keyword',
                'Book a consultation call',
                'Share or forward the email',
                'Download additional resources'
            ],
            'next_step': 'email_action_selected'
        }

    elif step == 'email_action_selected':
        return {
            'message': "What tone best represents your brand for this email?",
            'options': [
                'Direct and straightforward',
                'Warm and story-driven',
                'Persuasive and compelling',
                'Educational and informative'
            ],
            'next_step': 'email_tone_selected'
        }

    elif step == 'email_tone_selected':
        return {
            'message': "Would you like subject line suggestions included?",
            'options': ['Yes, include subject lines', 'No, email content only'],
            'next_step': 'generate_content'
        }

    return {
        'message': "Processing your request to generate content.",
        'next_step': 'generate_content'
    }
    
def build_content_prompt(next_response, state, prompt):
    if (next_response['next_step'] == 'generate_content' or 
            next_response.get('needs_ai_response') or 
            next_response.get('conversation_mode')):

        full_context = state  # <- use your state from DB

        if next_response['next_step'] == 'generate_content':
            return f"""
            Generate professional {full_context.get('content_type')} content based on:
            
            Content Type: {full_context.get('content_type')}
            Goal: {full_context.get('goal')}
            User Requirements: {full_context.get('data')}
            
            CRITICAL FORMATTING REQUIREMENTS:
            - Use proper line breaks and spacing throughout
            - For emails: Add blank lines between paragraphs, after subject line, before and after lists
            - For carousels: Separate each slide clearly with proper spacing
            - For reels: Format with clear sections and proper line breaks
            - Make content easy to read with professional spacing
            - No cramped text - always use adequate white space
            - Structure content with clear visual separation between sections
            
            Content Requirements:
            - Create well-structured, professional content
            - Make it ready for immediate use
            - Align with the specified goal and audience
            - No emojis or special characters
            """

        elif next_response.get('conversation_mode'):
            return f"""
            You are now in conversation mode with the user. They have already completed the content creation process.
            
            Previous Context:
            - Content Type: {full_context.get('content_type', 'Not specified')}
            - Goal: {full_context.get('goal', 'Not specified')}
            - Generated Content: {'Yes' if full_context.get('content_generated') else 'No'}
            
            User's current message: "{prompt}"
            
            Respond as a professional content creation expert. Handle:
            - Content modifications and improvements
            - Questions about content strategy
            - Requests for different variations
            - General content marketing advice
            - Follow-up questions about the generated content
            
            Be helpful, professional, and specific to their content creation needs. 
            Always format responses properly with line breaks and no emojis.
            """

        else:
            return f"""
            User message: {prompt}
            
            Previous context: {full_context}
            
            Provide a helpful, professional response related to content creation. 
            Format your response professionally with proper spacing and no emojis.
            """
    return ""  # fallback if no conditions met
