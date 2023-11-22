from django.core.management.base import BaseCommand
from rules.models import GermanVerb, EnglishVerb, EnglishAdjective, EnglishNoun
from inflex import Noun, Verb, Adjective
import csv


class Command(BaseCommand):
    help = "Imports Declensions"

    def add_arguments(self, parser):
        parser.add_argument("--germanverbs", type=str)

    def handle(self, *args, **options):
        if options["germanverbs"]:
            with open(options["germanverbs"]) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    text = row["infinitiv"]

                    try:
                        model = GermanVerb.objects.get(base_form=text)
                    except GermanVerb.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German verb '{text}' does not exist, skipping"
                            )
                        )
                        continue

                    if model.past_participle is not None:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German verb '{text}' already has 'past_participle' filled, skipping"
                            )
                        )
                        continue

                    model.present_ich = row["present_ich"]
                    model.present_du = row["present_du"]
                    model.present_pronoun = row["present_pronoun"]
                    model.past_tense_ich = row["past_tense_ich"]
                    model.past_participle = row["past_participle"]
                    model.conjunctive_ich = row["conjunctive_ich"]
                    model.imperativ_singular = row["imperativ_singular"]
                    model.imperativ_plural = row["imperativ_plural"]
                    model.helping_verb = row["helping_verb"]
                    model.infinitiv_zu = row["infinitiv_zu"]
                    model.save()

                    self.stdout.write(
                        self.style.ERROR(
                            f"Successfully updated German verb '{model.base_form}'"
                        )
                    )

        models = EnglishVerb.objects.filter(past_tense=None)
        for model in models:
            inflex = Verb(model.base_form)
            model.past_tense = inflex.past()
            model.past_participle = inflex.past_part()
            model.present_participle = inflex.pres_part()
            model.third_person_singular = inflex.singular()
            model.save()
            self.stdout.write(
                self.style.ERROR(
                    f"Successfully updated English verb '{model.base_form}'"
                )
            )

        models = EnglishAdjective.objects.filter(comparative=None)
        for model in models:
            inflex = Adjective(model.base_form)
            if model.base_form.isupper():
                model.comparative = model.base_form
                model.superlative = model.base_form
            else:
                model.comparative = inflex.comparative()
                model.superlative = inflex.superlative()
            model.is_absolute = False
            model.save()
            self.stdout.write(
                self.style.ERROR(
                    f"Successfully updated English adjective '{model.base_form}'"
                )
            )

        models = EnglishNoun.objects.filter(plural=None)
        for model in models:
            inflex = Noun(model.base_form)
            model.plural = inflex.plural()
            model.save()
            self.stdout.write(
                self.style.ERROR(
                    f"Successfully updated English noun '{model.base_form}'"
                )
            )
