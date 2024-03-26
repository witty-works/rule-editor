from django.core.management.base import BaseCommand
from rules.models import Rule, TrainingSentence, Alternative
from openai import AzureOpenAI
from os import environ
import json
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Translates english rules into german and saves them in the database."

    def handle(self, *args, **options):
        try:
            rules = Rule.objects.all()
        except Exception as e:
            logger.error(f"Failed to fetch rules: {e}")
            return

        try:
            with open('rules/management/commands/diversity_dimensions.json', 'r') as file:
                all_diversity_dimensions = json.load(file)
        except Exception as e:
            logger.error(f"Failed to load diversity dimensions: {e}")
            return

        client = AzureOpenAI(
            azure_endpoint="https://openai-test-solveig-helland.openai.azure.com/",
            api_key=environ.get("AZURE_OPENAI_KEY"),
            api_version="2024-02-15-preview"
        )

        for rule in rules.order_by('?'): # Randomize the order of rules
            try:
                if rule.language != "en":
                    continue

                alternatives = Alternative.objects.filter(rule_id=rule.id, is_inspiration=0)
                example_sentences = TrainingSentence.objects.filter(rule=rule)

                #if no alternatives or example sentences, skip rule
                if len(alternatives) == 0 or len(example_sentences) == 0:
                    # self.stdout.write(self.style.ERROR(f"Skipping rule {rule} because it has no alternatives or example sentences"))
                    continue

                dimension_key = rule.diversity_dimension_json[0]
                if dimension_key.endswith('_advanced'):
                    dimension_key = dimension_key[:-9]

                dimension_info = all_diversity_dimensions[dimension_key]
                dimension_info = str(dimension_info).replace("'", '"')

                rule_formatted_for_translation = {
                    "rule_category": dimension_key,
                    "rule_specification":{
                        "rule_trigger": rule.text_id,
                        "lemma": rule.lemma,
                        "word_type": rule.word_types,
                        "lemma_type": rule.type,
                        "entity_type": rule.entity_type,
                        "pluralism": rule.pluralization
                    },
                    "alternatives":{
                        "alternative_prio_1": alternatives[0].lemma if len(alternatives) > 0 else "",
                        "alternative_prio_2": alternatives[1].lemma if len(alternatives) > 1 else "",
                        "alternative_prio_3": alternatives[2].lemma if len(alternatives) > 2 else ""
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1": example_sentences[0].text if len(example_sentences) > 0 else "",
                        "true_positive_sentence_2": example_sentences[1].text if len(example_sentences) > 1 else ""
                    },
                }
                rule_formatted_for_translation = str(rule_formatted_for_translation).replace("'", '"')
                self.stdout.write(self.style.SUCCESS(f"Translating rule: {rule_formatted_for_translation}"))
        
                prompt=[
                {
                    "role": "system",
                    "content": "You are tasked with the role of an inclusive rule translator. Your input consists of an inclusive category description and a JSON object containing English descriptions of language rules. Your goal is to translate these rules into German while considering rule category. The translation can be direct or adapted to better align with German cultural or linguistic nuances. Focus on translations that adjusts phrases and concepts to fit the cultural and linguistic context of the target language, while maintaining the original intent. Return only the translations as a json where every field is filled.  If there is no good German translation of the rule trigger, return an empty json. \n\nExplanation of JSON fields: \nrule_category: category that inclusivity rule belongs to\nrule_trigger: word or saying that triggers rule by being un inclusive\nlemma: dictionary form of rule_trigger, or citation form of a set of word forms\nword_type: ’|' separated list of word types (n, pron, a, adv, v, conj, emoji, num, card) and optional modifiers: '=' case sensitive unlemmatized, '~' case insensitive unlemmatize, '-' case sensitive lemmatized\nlemma_type: Should the rule check on part of the lemma (either: default (full lemma), prefix, suffix, substring)\nentity_type: If the rule should only match on a specific entity type (either: default (nothing), name, non_name, person, non_person, number, datetime)\npluralism: Show alternative in case rule triggered on singular/plural/both (either: default (both), singular_only, plural_only )\nalternatives: more inclusive alternatives to the rule_trigger, ranked from best to worst. If the best alternative is to remove the word, the alternative should be ‘-‘.  \ntrue_positive_examples: sentences containing the rule_trigger in that exact form to test if rule gets triggered. The rule trigger should fit organically in the sentence, no quotes. \n\nExamples of correct translations: \n{\n   \"rule_category\":\"vision\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"blind as a bat\",\n      \"lemma\":\"blind as a bat\",\n      \"word_type\":\"~a|||~n\",\n      \"lemma_type\":\"default\",\n      \"entity_type\":\"default\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1\":\"blind\",\n      \"alternative_prio_2\":\"vision impaired person\",\n      \"alternative_prio_3\":\"person who is blind\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"She was as blind as a bat when it came to understanding the complex math problem.\",\n      \"true_positive_sentence_2\":\"He was so blind as a bat that he couldn't even see the sign in front of him.\"\n   }\n}\n=> \n{\n   \"rule_category\":\"vision\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"blind wie eine Fledermaus\",\n      \"lemma\":\"blind wie eine Fledermaus\",\n      \"word_type\":\"a||~|n\",\n      \"lemma_type\":\"default\",\n      \"entity_type\":\"default\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1\":\"schlecht sehen\",\n      \"alternative_prio_2\":\"mit schwachem Sehvermögen\",\n      \"alternative_prio_3\":\"\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"Er war so blind wie eine Fledermaus, dass er das Schild vor ihm nicht sehen konnte.\",\n      \"true_positive_sentence_2\":\"Sie ist blind wie eine Fledermaus.\"\n   }\n}\n_________\n{\n   \"rule_category\":\"sexual_orientation\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"play for the other team\",\n      \"lemma\":\"play for the other team\",\n      \"word_type\":\"v|||a|n\",\n      \"lemma_type\":\"default\",\n      \"entity_type\":\"default\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1\":\"identify as lesbian\",\n      \"alternative_prio_2\":\"identify as gay\",\n      \"alternative_prio_3\":\"identify as a member of the LGBT+ community\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"Does he play for the other team?\",\n      \"true_positive_sentence_2\":\"She plays for the other team.\"\n   }\n}\n=> \n{\n   \"rule_category\":\"sexual_orientation\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"vom anderen Ufer\",\n      \"lemma\":\"vom anderen Ufer\",\n      \"word_type\":\"|a|n\",\n      \"lemma_type\":\"default\",\n      \"entity_type\":\"default\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1”:”-“,\n      \"alternative_prio_2\":\"schwul\",\n      \"alternative_prio_3\":\"lesbisch\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"Er ist vom anderen Ufer.\",\n      \"true_positive_sentence_2\":\"Sie hat mir erzählt, dass sie vom anderen Ufer ist.\"\n   }\n}\n_________\n   {\n   \"rule_category\":\"leadership\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"boss\",\n      \"lemma\":\"boss\",\n      \"word_type\":\"n\",\n      \"lemma_type\":\"default\",\n      \"entity_type\":\"default\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1\":\"management\",\n      \"alternative_prio_2\":\"administration\",\n      \"alternative_prio_3\":\"supervisor\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"I'll have to ask my boss about this decision.\",\n      \"true_positive_sentence_2\":\"The boss is always right.\"\n   }\n}\n=> \n{\n   \"rule_category\":\"leadership\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"Chef\",\n      \"lemma\":\"Chef\",\n      \"word_type\":\"n\",\n      \"lemma_type\":\"suffix\",\n      \"entity_type\":\"non_person\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1\":\"Leitungsperson\",\n      \"alternative_prio_2\":\"CEOs\",\n      \"alternative_prio_3\":\"verantwortliche Person\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"Der Chef hat die Entscheidung getroffen.\",\n      \"true_positive_sentence_2\":\"Er ist der Chef des Unternehmens.\"\n   }\n}\n_________\n{\n   \"rule_category\":\"ableism\",\n   \"rule_specification\":{\n      \"rule_trigger\":\"herp-derp\",\n      \"lemma\":\"herp-derp\",\n      \"word_type\":\"n\",\n      \"lemma_type\":\"default\",\n      \"entity_type\":\"default\",\n      \"pluralism\":\"default\"\n   },\n   \"alternatives\":{\n      \"alternative_prio_1\":\"-\",\n      \"alternative_prio_2\":\"\",\n      \"alternative_prio_3\":\"\"\n   },\n   \"true_positive_examples\":{\n      \"true_positive_sentence_1\":\"He was talking in a herp-derp manner, making no sense at all.\",\n      \"true_positive_sentence_2\":\"The dialogue in that comedy sketch was pure herp-derp.\"\n   }\n}\n=>\n{}\n_________"
                },
                {
                    "role": "user",
                    "content": "category information: " + dimension_info + "rule to translate: " + rule_formatted_for_translation
                },
                ]
                chat_completion = client.chat.completions.create(
                model="gpt40125preview",#try gpt-4
                messages = prompt,
                temperature=1.2,
                max_tokens=256,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
                )

                # Append results to file
                with open('rules/management/commands/translated_rules.json', 'a') as file:
                    file.write(json.dumps(rule_formatted_for_translation) + '\n')
                    file.write(json.dumps(chat_completion.choices[0].message.content) + '\n')

                self.stdout.write(self.style.SUCCESS(f'Generated rule: {chat_completion.choices[0].message.content}'))

            except Exception as e:
                # Log the error and skip to the next rule
                logger.error(f"Error processing rule {rule.id}: {e}")
                continue  # Move to the next iteration

