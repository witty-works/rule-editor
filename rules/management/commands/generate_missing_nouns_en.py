from django.core.management.base import BaseCommand
from rules.models import (
    EnglishNoun,
    GermanNoun,
    NerTypeEnum,
    Rule,
    DiversityDimension,
)
import logging
import requests

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Finds missing nouns for english and adds them to the db."

    def add_arguments(self, parser):
        parser.add_argument("--debug", type=str, default=True)
        parser.add_argument("--language", type=str, default="en")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        nouns = GermanNoun.objects.filter(
            ner__in=[NerTypeEnum.PERSON, NerTypeEnum.GROUP],
            male_form=None,
            # base_form="Designer",
        )

        openly_discriminating_ddds = DiversityDimension.objects.filter(
            proficiency_level="openly_discriminating"
        )
        openly_discriminating = []
        for openly_discriminating_ddd in openly_discriminating_ddds:
            openly_discriminating.append(openly_discriminating_ddd.name)
        openly_discriminating = set(openly_discriminating)

        url = "http://localhost:5000/translate"
        q = ""
        data = {
            "source": "de",
            "target": "en",
            "format": "text",
            "alternatives": 0,
            "api_key": "",
        }

        for noun_de in nouns:
            self.stdout.write(
                self.style.WARNING(f"Processing noun: {noun_de.base_form}")
            )

            try:
                result = ""
                rules = Rule.objects.filter(lemma=noun_de.base_form)
                if len(rules) and not openly_discriminating.isdisjoint(
                    rules[0].diversity_dimension_json
                ):
                    self.stdout.write(
                        self.style.ERROR(
                            f"Skipping openly_discriminating: {noun_de.base_form}"
                        )
                    )
                    continue

                data["q"] = q + noun_de.base_form
                r = requests.post(url, json=data, timeout=5)
                result = r.json()
                result = result["translatedText"]

                if result.endswith("s"):
                    result = result.removesuffix("s")

                result = result.split()[-1]
                if not result.isupper():
                    result = result.lower()

                check_data = {
                    "q": result,
                    "source": "en",
                    "target": "de",
                    "format": "text",
                    "alternatives": 0,
                    "api_key": "",
                }

                r = requests.post(url, json=check_data, timeout=5)
                check_result = r.json()
                check_result = check_result["translatedText"]
                if not noun_de.base_form.lower().endswith(check_result.lower()):
                    self.stdout.write(
                        self.style.ERROR(
                            f"Skipping unsave translation '{result}' vs. '{check_result}': {noun_de.base_form}"
                        )
                    )
                    continue

                noun_en = EnglishNoun()
                noun_en.base_form = result
                noun_en.ner = noun_de.ner
                noun_en.comment = f"Translated from German '{noun_de.base_form}'"
                noun_en.fill_declensions()
                noun_en.save()
            except Exception as e:
                logger.error(f"Failed to store noun '{result}': {e}")
