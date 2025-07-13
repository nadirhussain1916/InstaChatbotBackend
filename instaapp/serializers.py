from rest_framework import serializers
from .models import Instagram_User,InstagramPost,ChatThread, ChatMessage

        
class CarouselGeneratorSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=['Humble', 'Origin', 'Product'],required=False,default='Humble')
    description = serializers.CharField(required=True,max_length=2000)
    slides = serializers.IntegerField(required=False, default=1, max_value=10)
    inspiration = serializers.CharField(max_length=5000, required=False, allow_blank=True,default='')

class InstagramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instagram_User
        fields = ['id', 'username', 'full_name', 'followers', 'posts', 'profile_pic']

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
    


