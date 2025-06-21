from rest_framework import serializers
from .models import Instagram_User,InstagramPost
  
        
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