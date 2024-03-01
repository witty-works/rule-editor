from django.core.management.base import BaseCommand
from rules.admin import apply_rule
from rules.models import Rule, TrainingSentence
import json

class Command(BaseCommand):
    help = "Checks that rules work as expected (training sentence response is not empty)"    
        
    def handle(self, *args, **options):
        rules = Rule.objects.all()
        with open('empty_responses.txt', 'w') as file:
            for rule in rules:
                training_sentences = TrainingSentence.objects.filter(rule=rule)
                if len(training_sentences):
                    for sentence in training_sentences:
                        if sentence.is_false_positive: #dont expect this to work yet
                            continue
                        response = apply_rule({"rule": rule.id, "text": sentence.text})                    
                        if len(response) == 0:
                            self.stdout.write(self.style.ERROR(f"Response is empty for rule {rule} and sentence {sentence}"))
                            file.write(f"Response is empty for rule {rule} and sentence {sentence}\n")
                # else: #uncomment as extra check when we have generated training sentences
                    # self.stdout.write(self.style.ERROR(f"No training sentences for rule {rule}"))      

