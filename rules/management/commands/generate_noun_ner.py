from django.core.management.base import BaseCommand
from rules.models import (
    EnglishNoun,
    GermanNoun,
    NerTypeEnum,
)
from openai import AzureOpenAI
from os import environ
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate NER information for english and german nouns."

    def add_arguments(self, parser):
        parser.add_argument("--debug", type=str, default=True)
        parser.add_argument("--language", type=str, default="en")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        language = options["language"]
        limit = options["limit"]

        try:
            objects = GermanNoun.objects if language == "de" else EnglishNoun.objects
            nouns = objects.exclude(ner__isnull=False)
            if limit is not None and limit > 0:
                nouns = nouns[0:limit]
        except Exception as e:
            logger.error(f"Failed to fetch nouns: {e}")
            return

        client = AzureOpenAI(
            azure_endpoint=environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=environ.get("AZURE_OPENAI_KEY"),
            api_version=environ.get("AZURE_OPENAI_VERSION"),
        )

        instruction = '''You are an advanced Named Entity Recognition (NER) system. Your task is to classify a given noun, which will be either in English or German, into one of the following categories:
- person
- group
- location
- organization
- thing
- misc

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
  - Output: "misc"'''

        for noun in nouns:
            self.stdout.write(self.style.WARNING(f"Processing noun: {noun}"))
            try:
                prompt = [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": "Noun to classify: " + noun.base_form},
                ]
                chat_completion = client.chat.completions.create(
                    model=environ.get("AZURE_OPENAI_MODEL"),
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
