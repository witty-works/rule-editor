from django.core.management.base import BaseCommand
from rules.models import Rule
from django.db.models import Q
from django.db.models import F, Func

import logging

logger = logging.getLogger(__name__)


class JsonArrayLength(Func):
    ...
    function = "json_array_length"
    ...

    def as_sqlite(self, compiler, connection, **extra_context):
        return super().as_sql(
            compiler,
            connection,
            function="json_array_length",
            template="%(function)s(%(expressions)s)",
            **extra_context,
        )


class Command(BaseCommand):
    help = "Fix the word type, by using the auto word type for all rules with failing test sentences"

    def add_arguments(self, parser):
        parser.add_argument("--lang", type=str, required=True)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--force", type=str, default=False)
        parser.add_argument("--tokenize", type=bool, default=True)
        parser.add_argument("--token-min-count", type=int, default=None)
        parser.add_argument("--has-failing", type=bool, default=None)

    def handle(self, *args, **options):
        lang = options["lang"]
        limit = options["limit"]
        force = options["force"]
        tokenize = options["tokenize"]
        token_min_count = options["token_min_count"]
        has_failing = options["has_failing"]

        rule = None

        try:
            rules = Rule.objects.filter(language=lang)

            if has_failing is not None:
                rules = rules.filter(has_failing_training_sentence=has_failing)

            if token_min_count is not None:
                pass
            #    rules = rules.annotate(
            #        token_count=Func(F("word_types_json"), function="json_array_length")
            #    )
            #    rules = rules.filter(token_count__gte=token_min_count)

            elif limit is not None and limit > 0:
                rules = rules[0:limit]

            count = 0
            for rule in rules:
                if limit is not None and count >= limit:
                    break

                if token_min_count is not None and token_min_count > len(
                    rule.word_types_json
                ):
                    continue

                count += 1
                self.stdout.write(self.style.WARNING(f"Processing rule: {rule}"))

                if force:
                    if rule.word_types != "":
                        rule.word_types = ""

                    rule.save()

                    self.stdout.write(self.style.WARNING(f"Updated word_types_json"))
                elif tokenize:
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
            if rule is not None:
                logger.error(f"Failed processing rule '{rule}': {e}")
            else:
                logger.error(f"Failed : {e}")
