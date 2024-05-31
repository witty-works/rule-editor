from django.core.management.base import BaseCommand
from rules.models import (
    EnglishNoun,
    GermanNoun,
    Rule,
)
from openai import AzureOpenAI
from os import environ
import json
import logging
from datetime import date

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = (
        "Generate NER information for english and german nouns."
    )

    def handle(self, *args, **options):
        language = "en"  # CHANGE THIS TO SWITCH BETWEEN LANGUAGES ("en" or "de")
        try:
            nouns = []
            
            if language == "de":
                nouns = GermanNoun.objects.all()
            else:
                nouns = EnglishNoun.objects.all()

        except Exception as e:
            logger.error(f"Failed to fetch nouns: {e}")
            return

        client = AzureOpenAI(
            azure_endpoint=environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=environ.get("AZURE_OPENAI_KEY"),
            api_version="2024-02-15-preview",
        )
        instruction = ""
        with open("rules/management/commands/ner_gen_prompt.txt", "r") as file:
            instruction = file.read()

        for noun in nouns:
            print(f"Processing noun: {noun}")
            try:
                prompt = [
                    { "role": "system",  "content": instruction },
                    { "role": "user", "content": "Noun to classify: " +  str(noun) },
                ]
                chat_completion = client.chat.completions.create(
                    model="gpt40125preview",
                    messages=prompt,
                    temperature=0.7,
                    max_tokens=200,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                )

                try:
                    result = chat_completion.choices[0].message.content

                    possible_entities = ['Person', 'Group', 'Location', 'Organization', 'Location', 'Thing', 'Misc']
                    found_entity_value = ''
                    for entity in possible_entities:
                        if entity in result:
                            found_entity_value = entity
                            break 

                    if found_entity_value == '':
                        print(f"Failed to find entity for noun {noun}")
                        continue

                    print(f"Found entity: {found_entity_value}")
                        
                    #update the noun with the entity
                    # if language == "de":
                    #     GermanNoun.objects.filter(id=noun.id).update(entity=found_entity_value)
                    # else:
                    #     EnglishNoun.objects.filter(id=noun.id).update(entity=found_entity_value)
                except Exception as e:
                    logger.error(f"Error processing noun: {e}")
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
