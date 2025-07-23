from django.contrib import admin
from .models import SystemPrompt

@admin.register(SystemPrompt)
class SystemPromptAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    search_fields = ['name']
