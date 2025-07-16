from django.db import models
from django.contrib.auth.models import User
import uuid
from django.db import models

class Instagram_User(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='instagram_profile')
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=151)
    followers = models.PositiveIntegerField(null=True, blank=True)
    posts = models.PositiveIntegerField(null=True, blank=True)
    profile_pic = models.ImageField(upload_to='instagram/', null=True, blank=True)
    password = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return self.username


class InstagramPost(models.Model):
    user = models.ForeignKey('Instagram_User', on_delete=models.CASCADE, related_name='instagram_posts')
    post_url = models.URLField(max_length=2500)
    caption = models.TextField(blank=True, null=True)
    media_url = models.URLField(max_length=2500,blank=True, null=True)  # Image or video URL
    thumbnail_url = models.ImageField(upload_to='thumbnails/', null=True, blank=True)
    post_type = models.CharField(max_length=50, choices=[
        ('image', 'Image'),
        ('video', 'Video'),
        ('reel', 'Reel'),
        ('carousel', 'Carousel'),
        ('unknown', 'Unknown')
    ], default='unknown')
    likes = models.PositiveIntegerField(blank=True, null=True)
    comments = models.PositiveIntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(blank=True, null=True)
    shortcode = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.shortcode or self.post_url}"

class ConversationThread(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']

class Message(models.Model):
    MESSAGE_TYPES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    thread = models.ForeignKey(ConversationThread, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES)
    content = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        
class onBoardingAnswer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()

    def __str__(self):
        return f"{self.user.username} - {self.question}"
    
class ChatThread(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_threads")
    thread_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)  # ✅ New field
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.JSONField(default=dict, blank=True, null=True)


    def __str__(self):
        return f"Chat {self.id} - {self.user.username}"

class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=10, choices=[("user", "User"), ("ai", "AI")])
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    state = models.JSONField(default=dict, blank=True, null=True)  # ✅ new field

    def __str__(self):
        return f"{self.sender.upper()} - {self.message[:30]}"