from django.core.management.base import BaseCommand
from rules.models import (
    EnglishNoun,
    GermanNoun,
    FrenchNoun,
    NerTypeEnum,
    GenderTypeEnum,
)
from openai import AzureOpenAI
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate NER information for english and german nouns."

    def add_arguments(self, parser):
        parser.add_argument("--debug", type=str, default=False)
        parser.add_argument("--language", type=str, default="en")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--force", type=bool, default=False)

    def handle(self, *args, **options):
        language = options["language"]
        limit = options["limit"]
        force = options["force"]

        try:
            if language == "de":
                objects = GermanNoun.objects
            elif language == "en":
                objects = EnglishNoun.objects
            elif language == "fr":
                objects = FrenchNoun.objects

            nouns = objects.all() if force else objects.filter(ner__isnull=True)
            if limit is not None and limit > 0:
                nouns = nouns[0:limit]
        except Exception as e:
            logger.error(f"Failed to fetch nouns: {e}")
            return

        client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_KEY,
            api_version=settings.AZURE_OPENAI_VERSION,
        )

        instruction = '''You are an advanced Named Entity Recognition (NER) system. Your task is to classify a given noun, which will be either in English, French or German, into one of the following categories:
- person
- group
- location
- organization
- thing
- misc
- animal

Example Inputs and Outputs:
- Input: "Office"
  - Output: "location"
- Input: "freak"
  - Output: "person"
- Input: "libtard"
  - Output: "person
- Input: "Paris"
  - Output: "location"
- Input: "outdoor"
  - Output: "location"
- Input: "Lagerraum" (German for "storage room")
  - Output: "location"
- Input: "Google"
  - Output: "organization"
- Input: "Greenpeace"
  - Output: "organization"
- Input: "Ministerium" (German for "ministry" or "department")
  - Output: "organization"
- Input: "Schule" (German for "school")
  - Output: "organization"
- Input: "Gruppe" (German for "group")
  - Output: "group"
- Input: "team"
  - Output: "group"
- Input: "Buch" (German for "book")
  - Output: "thing"
- Input: "house"
  - Output: "thing"
- Input: "fork"
  - Output: "thing"
- Input: "Luft" (German for "air")
  - Output: "misc"
- Input: "Aufgabe" (German for "task")
  - Output: "misc"
- Input: "action"
  - Output: "misc"
- Input: "grief"
  - Output: "misc"
- Input: "element"
  - Output: "misc"
- Input: "bureau" (French for "office")
  - Output: "location"
- Input: "étrange" (French for "weird" or "strange")
  - Output: "person"
- Input: "Paris" (French for "Paris")
  - Output: "location"
- Input: "extérieur" (French for "outdoor")
  - Output: "location"
- Input: "Google" (French for "Google")
  - Output: "organization"
- Input: "école" (French for "school")
  - Output: "organization"
- Input: "groupe" (French for "group")
  - Output: "group"
- Input: "livre" (French for "book")
  - Output: "thing"
- Input: "maison" (French for "house")
  - Output: "thing"
- Input: "fourchette" (French for "fork")
  - Output: "thing"
- Input: "air" (French for "air")
  - Output: "misc"
- Input: "tâche" (French for "task")
  - Output: "misc"
- Input: "action" (French for "action")
  - Output: "misc"
- Input: "chagrin" (French for "grief")
  - Output: "misc"
- Input: "élément" (French for "element")
  - Output: "misc"
- Input: "chat" (French for "cat")
  - Output: "animal"
- Input: "Katze" (German for "cat")
  - Output: "animal"
- Input: "dog"
  - Output: "animal"'''

        for noun in nouns:
            if (
                noun.female_form
                or noun.male_form
                or (
                    noun.gender_1 == GenderTypeEnum.MASCULINE
                    and noun.gender_2 == GenderTypeEnum.FEMININE
                )
            ):
                continue

            self.stdout.write(self.style.WARNING(f"Processing noun: {noun}"))
            try:
                prompt = [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": "Noun to classify: " + noun.base_form},
                ]
                chat_completion = client.chat.completions.create(
                    model=settings.AZURE_OPENAI_MODEL,
                    messages=prompt,
                    temperature=0.7,
                    max_tokens=200,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                )

                try:
                    result = chat_completion.choices[0].message.content

                    possible_entities = [
                        NerTypeEnum.PERSON,
                        NerTypeEnum.GROUP,
                        NerTypeEnum.ORGANIZATION,
                        NerTypeEnum.LOCATION,
                        NerTypeEnum.THING,
                        NerTypeEnum.MISC,
                        NerTypeEnum.ANIMAL,
                    ]

                    found_entity_value = None
                    for entity in possible_entities:
                        if entity in result:
                            found_entity_value = entity
                            break

                    if found_entity_value is None:
                        self.stdout.write(
                            self.style.ERROR(f"Failed to find entity for noun {noun}")
                        )
                        continue

                    # update the noun with the entity
                    noun.ner = found_entity_value
                    noun.save()

                    self.stdout.write(
                        self.style.SUCCESS(f"Updated ner: {found_entity_value}")
                    )
                except Exception as e:
                    logger.error(f"Error processing noun: {e}")

                    if options["debug"]:
                        with open(
                            "rules/management/commands/ner_gen_errors.json", "a"
                        ) as file:  # REMOVE THIS AFTER INITIAL RULE GENERATION
                            file.write("Error: " + str(e) + "\n")
                            file.write("Noun: " + str(noun) + "\n")
                            file.write("Result: " + str(result) + "\n")
            except Exception as e:
                # Log the error and skip to the next rule
                logger.error(f"Error processing noun {noun}: {e}")

                continue  # Move to the next iteration
