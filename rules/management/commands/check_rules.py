from django.core.management.base import BaseCommand
from rules.admin import apply_rule
from rules.models import Rule, TrainingSentence


class Command(BaseCommand):
    help = (
        "Checks that rules work as expected (training sentence response is not empty)"
    )

    def handle(self, *args, **options):
        new_failing_rules = failing_rules = 0

        rules = Rule.objects.all()
        for rule in rules:
            self.stdout.write(self.style.WARNING(f"Checking rule {rule}"))

            training_sentences = TrainingSentence.objects.filter(rule=rule)
            if len(training_sentences):
                for sentence in training_sentences:
                    if sentence.is_false_positive:  # dont expect this to work yet
                        continue
                    try:
                        response = apply_rule({"rule": rule.id, "text": sentence.text})
                    except:
                        continue
                    if len(response) == 0:
                        if not sentence.is_false_positive:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"Response is empty for rule {rule} and sentence {sentence}"
                                )
                            )
                            failing_rules += 1
                            new_failing_rules += self.mark_as_failing(rule)
                    elif sentence.is_false_positive:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Response is not for rule {rule} and sentence {sentence} for a false positive"
                            )
                        )
                        failing_rules += 1
                        new_failing_rules += self.mark_as_failing(rule)
            else:
                self.stdout.write(
                    self.style.ERROR(f"No training sentences for rule {rule}")
                )

        if failing_rules:
            self.stdout.write(
                self.style.ERROR(
                    f"There are {failing_rules} with {new_failing_rules} newly failing rules"
                )
            )

    def mark_as_failing(self, rule: Rule):
        if rule.has_failing_training_sentence:
            return 0

        rule.has_failing_training_sentence = True
        rule.save()
        return 1
