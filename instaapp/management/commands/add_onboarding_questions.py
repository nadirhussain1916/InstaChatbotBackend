# yourapp/management/commands/add_onboarding_questions.py

from django.core.management.base import BaseCommand
from instaapp.models import Question

class Command(BaseCommand):
    help = 'Insert 10 onboarding questions into the database'

    def handle(self, *args, **kwargs):
        questions = [
            "What is your current job role?",
            "What is your biggest challenge right now?",
            "What are you hoping to achieve using our platform?",
            "How did you hear about us?",
            "What industry are you in?",
            "What’s your preferred method of learning?",
            "Do you have experience with similar tools?",
            "How often do you plan to use this platform?",
            "Would you like to receive updates and tips via email?",
            "What feature are you most excited to try?"
        ]

        for text in questions:
            Question.objects.get_or_create(text=text)

        self.stdout.write(self.style.SUCCESS('✅ Successfully added 10 onboarding questions.'))
