from typing import Optional
from django.core.management.base import BaseCommand
from django.db import IntegrityError

from rules.models import (
    Alternative,
    FrenchNoun,
    NerTypeEnum,
    GenderTypeEnum,
    Rule,
)
from pluralizefr import pluralize


class Command(BaseCommand):
    help = "Add missing gendered nouns"

    def add_arguments(self, parser):
        parser.add_argument("--lang", type=str, required=True)
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        lang = options["lang"]
        limit = options["limit"]

        alternatives = Alternative.objects.filter(
            language=lang,
            is_gendered_noun=True,
        )
        if limit is not None and limit > 0:
            alternatives = alternatives[0:limit]

        count = 0
        for alternative in alternatives:
            if limit is not None and count >= limit:
                break

            rule = Rule.objects.get(id=alternative.rule_id)
            if rule.word_types != "n" and rule.actual_word_types != "n":
                self.stdout.write(
                    self.style.WARNING(f"Skipping alternative: {alternative} due to rule {rule.word_types} / {rule.actual_word_types}")
                )
                continue

            count += 1

            lemmas = alternative.lemma.split("~")
            if lemmas[0] == lemmas[1]:
                alternative.lemma = lemmas[0]
                alternative.is_gendered_noun = False
            else:
                self.store_noun(lemmas[1], lemmas[0], None)

            self.store_noun(lemmas[0], None, lemmas[1])

            alternative.save()

            self.stdout.write(
                self.style.SUCCESS(f"Processed alternative: {alternative}")
            )

    def store_noun(
        self,
        base_form: str,
        male_form: Optional[str] = None,
        female_form: Optional[str] = None,
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
