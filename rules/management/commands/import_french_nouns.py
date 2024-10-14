from django.core.management.base import BaseCommand
from django.db import IntegrityError
from rules.models import FrenchNoun, Alternative, Rule, GenderTypeEnum, NerTypeEnum
from rules.pluralize_fr import pluralize


class Command(BaseCommand):
    help = "Imports the lemmatization"

    def handle(self, *args, **options):
        alternatives = Alternative.objects.filter(language="fr", is_gendered_noun=True)
        for alternative in alternatives:
            rule = Rule.objects.get(id=alternative.rule_id)
            if (rule.word_types is None or "n" not in rule.word_types) and (
                rule.actual_word_types is None or "n" not in rule.actual_word_types
            ):
                continue

            if "~" not in alternative.lemma:
                message = (
                    f"'~'' missing in {alternative} for rule '{alternative.rule_id}'"
                )

                self.stdout.write(self.style.ERROR(message))
                continue

            male_form, female_form = alternative.lemma.split("~")

            self.store_noun(male_form, None, female_form)
            self.store_noun(female_form, male_form, None)

    def store_noun(
        self, base_form: str, male_form: str | None, female_form: str | None
    ):
        try:
            french_noun = FrenchNoun()
            french_noun.gender_1 = (
                GenderTypeEnum.FEMININE
                if female_form is None
                else GenderTypeEnum.MASCULINE
            )
            french_noun.base_form = base_form
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
