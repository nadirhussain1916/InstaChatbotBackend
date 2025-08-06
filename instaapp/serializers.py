from rest_framework import serializers
from .models import Instagram_User,InstagramPost,ChatThread, ChatMessage,SystemPrompt

        
class CarouselGeneratorSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=['Humble', 'Origin', 'Product'],required=False,default='Humble')
    description = serializers.CharField(required=True,max_length=2000)
    slides = serializers.IntegerField(required=False, default=1, max_value=10)
    inspiration = serializers.CharField(max_length=5000, required=False, allow_blank=True,default='')

class InstagramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instagram_User
        fields = ['id', 'username', 'full_name', 'followers', 'posts', 'profile_pic','media_url']
class InstagramPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramPost
        fields = ['id', 'post_url', 'caption', 'media_url', 'thumbnail_url', 'post_type', 'likes', 'comments', 'timestamp', 'shortcode']
        




class ChatMsgSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['sender', 'message']

class ChatThreadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatThread
        fields = ['thread_id', 'title', 'created_at']
    

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'sender', 'message', 'timestamp']

class ChatSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()  # ✅ Use custom logic here

    class Meta:
        model = ChatThread
        fields = ['thread_id', 'created_at', 'messages']

    def get_messages(self, obj):
        # ✅ Return messages ordered by ID (ascending)
        ordered_messages = obj.messages.order_by('id')
        return ChatMessageSerializer(ordered_messages, many=True).data
    

class SystemPromptSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    content = serializers.CharField(required=True, allow_blank=False)
    is_active = serializers.BooleanField(required=True)
    
    class Meta:
        model = SystemPrompt
        fields = "__all__"

    def validate(self, data):
        if not data.get('name'):
            raise serializers.ValidationError({'name': 'This field is required.'})
        if not data.get('content'):
            raise serializers.ValidationError({'content': 'This field is required.'})
        if 'is_active' not in data:
            raise serializers.ValidationError({'is_active': 'This field is required.'})

        return data
    
    def validate_name(self, value):
        if self.instance is None and SystemPrompt.objects.filter(name=value).exists():
            raise serializers.ValidationError('A prompt with this name already exists.')
        return value