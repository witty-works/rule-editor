from django.core.management.base import BaseCommand
from django.db import IntegrityError

from rules.models import Rule, FrenchNoun, NerTypeEnum, GenderTypeEnum, TranslatableEnum
from pluralizefr import pluralize


class Command(BaseCommand):
    help = "Move article at the beginning to pattern"

    def add_arguments(self, parser):
        parser.add_argument("--lang", type=str, required=True)
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        lang = options["lang"]
        limit = options["limit"]

        rule = None

        rules = Rule.objects.filter(
            language=lang,
            lemma__startswith="un ",
            pattern__isnull=True,
            is_translatable__ne=TranslatableEnum.NO,
        )
        if limit is not None and limit > 0:
            rules = rules[0:limit]

        count = 0
        for rule in rules:
            if limit is not None and count >= limit:
                break

            count += 1
            self.stdout.write(self.style.WARNING(f"Processing rule: {rule}"))

            for alternative in rule.alternatives.all():
                alternative.lemma = alternative.lemma.removeprefix("un ").replace(
                    "~une ", "~"
                )
                if alternative.is_gendered_noun:
                    lemmas = alternative.lemma.split("~")
                    if lemmas[0] == lemmas[1]:
                        alternative.lemma = lemmas[0]
                        alternative.is_gendered_noun = False
                    else:
                        self.store_noun(lemmas[1], lemmas[0], None)

                    self.store_noun(lemmas[0], None, lemmas[1])
                else:
                    self.store_noun(alternative.lemma)

                if alternative.word_types:
                    word_types = alternative.word_types.split("|")
                    alternative.word_types = "|".join(word_types[1:])

                alternative.save()

            rule.lemma = rule.lemma.removeprefix("un ")
            rule.pattern = "article|l"
            rule.is_pattern_match = True
            if rule.word_types:
                word_types = rule.word_types.split("|")
                rule.word_types = "|".join(word_types[1:])
            rule.save()

    def store_noun(
        self,
        base_form: str,
        male_form: str | None = None,
        female_form: str | None = None,
    ):
        if " " in base_form:
            return False

        try:
            french_noun = FrenchNoun()
            french_noun.base_form = base_form

            # skip creating feminine noun for gender neutral noun
            if base_form == male_form:
                return False

            if base_form == female_form:
                french_noun.gender_1 = GenderTypeEnum.MASCULINE
                french_noun.gender_2 = GenderTypeEnum.FEMININE
            elif male_form or female_form:
                french_noun.gender_1 = (
                    GenderTypeEnum.FEMININE
                    if female_form is None
                    else GenderTypeEnum.MASCULINE
                )
                french_noun.male_form = male_form
                french_noun.female_form = female_form

            french_noun.ner = NerTypeEnum.PERSON
            french_noun.plural = pluralize(base_form)
            french_noun.save()
        except IntegrityError as e:
            return False

        message = f"Added {base_form}"
        self.stdout.write(self.style.SUCCESS(message))

        return True
