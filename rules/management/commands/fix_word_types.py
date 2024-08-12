from django.core.management.base import BaseCommand
from rules.models import Rule

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix the word type, by using the auto word type for all rules with failing test sentences"

    def add_arguments(self, parser):
        parser.add_argument("--lang", type=str)
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        lang = options["lang"]
        limit = options["limit"]

        try:
            rules = Rule.objects.filter(
                language=lang, has_failing_training_sentence=True
            )

            if limit is not None and limit > 0:
                rules = rules[0:limit]

            for rule in rules:
                self.stdout.write(self.style.WARNING(f"Processing rule: {rule}"))

                if rule.word_types_json == []:
                    rule.save()

                    self.stdout.write(self.style.WARNING(f"Updated word_types_json"))
                else:
                    tokens, lemmas, generated_word_types = rule.tokenize()
                    if rule.word_types != generated_word_types:
                        rule.word_types = generated_word_types
                        rule.has_failing_training_sentence = False
                        rule.save()

                        self.stdout.write(
                            self.style.WARNING(
                                f"Updated word type to {generated_word_types}"
                            )
                        )

        except Exception as e:
            logger.error(f"Failed processing rule '{rule}: {e}")
