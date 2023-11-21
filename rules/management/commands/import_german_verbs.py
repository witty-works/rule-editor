from django.core.management.base import BaseCommand
from rules.models import GermanVerb
import csv


class Command(BaseCommand):
    help = "Imports German Verb-Data"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)

    def handle(self, *args, **options):
        with open(options["file"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = row["infinitiv"]

                try:
                    verb = GermanVerb.objects.get(base_form=text)
                    message = f"Successfully updated verb '{text}'"
                except GermanVerb.DoesNotExist:
                    message = f"Verb '{text}' does not exist, skipping "
                    self.stdout.write(self.style.ERROR(message))
                    continue

                verb.present_ich = row["present_ich"]
                verb.present_du = row["present_du"]
                verb.present_pronoun = row["present_pronoun"]
                verb.past_tense_ich = row["past_tense_ich"]
                verb.past_participle = row["past_participle"]
                verb.conjunctive_ich = row["conjunctive_ich"]
                verb.imperativ_singular = row["imperativ_singular"]
                verb.imperativ_plural = row["imperativ_plural"]
                verb.helping_verb = row["helping_verb"]
                verb.infinitiv_zu = row["infinitiv_zu"]
                verb.save()
