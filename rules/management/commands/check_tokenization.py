from django.core.management.base import BaseCommand
from rules.models import Rule


class Command(BaseCommand):
    help = "Checks that tokenization work as expected for the word_types"

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str)
        parser.add_argument("--lang", type=str)

    def handle(self, *args, **options):
        new_failing_rules = new_passing_rules = failing_rules = 0

        results = []

        lang = options["lang"]

        rules = (
            Rule.objects.all()
            if lang is None
            else Rule.objects.filter(language=lang, word_types__ne=True)
        )

        for rule in rules:
            tokens, lemmas, word_types = rule.tokenize()
            if len(tokens) != len(rule.word_types.split("|")):
                self.stdout.write(
                    self.style.ERROR(
                        f"Tokenization of '{rule}' incorrect: '{rule.word_types}' vs '{word_types}'"
                    )
                )

            for word_type in rule.word_types.split("|"):
                if word_type not in [
                    "v",
                    "a",
                    "adv",
                    "n",
                    "pron",
                    "emoji",
                    "conj",
                    "num",
                    "card",
                    "article",
                ]:
                    self.style.ERROR(
                        f"Tokenization of '{rule}' incorrect: '{word_type}' typo"
                    )
