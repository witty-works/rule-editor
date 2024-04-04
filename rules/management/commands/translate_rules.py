from django.core.management.base import BaseCommand
from rules.models import DiversityDimension, Rule, RuleDiversityDimension, TrainingSentence, Alternative
from openai import AzureOpenAI
from os import environ
import json
import logging
from datetime import date

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
        # goldSample = ['eye-opener', 'tranny', 'policeman', 'goal-getter', 'witch', 'slant-eye', 'fat', 'in the front-line', 'illegal immigrant', 'midget', 'boss', 'light in the loafers', 'world-wide', 'man-power', 'fall on deaf ears', 'guys', 'partner', 'housekeeping', 'world leader', 'punctual Germans', 'blacklisting', 'crazy', 'homeless', 'merry christmas', 'going the extra mile', 'young', 'can\'t learn an old dog new tricks', 'tard', 'handicapped']
        # goldSampleRules = []
        # for term in goldSample:
        #     # Find a matching rule
        #     matching_rule = next((rule for rule in rules if rule.text_id == term), None)
        #     # If a matching rule is found, add it to goldSampleRules
        #     if matching_rule:
        #         goldSampleRules.append(matching_rule)

        for rule in rules.order_by('?'): # Randomize the order of rules
            try:
                if rule.language != "en":
                    continue

                alternatives = Alternative.objects.filter(rule_id=rule.id)
                example_sentences = TrainingSentence.objects.filter(rule=rule)

                # if no alternatives skip rule
                if len(alternatives) == 0:
                    self.stdout.write(self.style.ERROR(f"Skipping rule {rule} because it has no alternatives"))
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

                instruction = """Your task is to function as an inclusive rule translator, focusing on translating and adapting language rules from English into German. The translation process must consider the inclusivity and cultural nuances of the German-speaking audience. For each provided rule, ensure the translated rule trigger exists in the German dictionary and retains the original rule's intent without creating new words. If a direct translation of the rule trigger would not be considered problematic in German, do not translate the rule and return an empty JSON object instead. If multiple synonyms exist in German, choose the one with the most offensive connotation to ensure clarity on what needs to be avoided. Provide new, culturally relevant examples in German that include the rule trigger in a natural way. The alternatives suggested should be more inclusive and avoid other offensive terms, adapted to fit the German context. If the alternatives do not apply or make sense in German, it's acceptable to come up with new ones. Each translation must include filled fields in a JSON format, only excluding translations when a direct German equivalent of the rule trigger does not exist.
                    Explanation of JSON fields: 
                    - `rule_category`: The inclusivity category the rule belongs to.
                    - `rule_trigger`: The word or phrase that triggers the rule by being non-inclusive.
                    - `lemma`: The base form of the rule trigger, or the citation form of a set of word forms.
                    - `word_type`: Lists of word types (e.g., `n` for noun, `pron` for pronoun) separated by '|' with optional modifiers for case sensitivity and lemmatization.
                    - `alternatives`: More inclusive alternatives to the rule trigger, ranked from best to worst. If the best alternative is to remove the word entirely, the alternative should be ‘-‘.\
                    - `is_collective_noun`: alternative lemma referres to a collection of things taken as a whole. If it is a collective noun, it means do not pluralize.
                    - `is_gendered_noun`: If an alternative lemma contains gendered nouns then non gendered variations should be generated.
                    - `is_advanced`: alternative lemma is not a well understood concept.  
                    - `true_positive_examples`: Sentences that contain the rule_trigger in its exact lemma form to test if the rule is triggered.

                    Translations must accurately reflect the original rule's intent while being adapted for German cultural and linguistic nuances. Return translations as a JSON object. Make sure every field in the json is present, even if its left empty.

                    Examples of correct translations
                    1. Vision Category Example:
                    Original:
                    {
                    "rule_category":"vision",
                    "rule_specification":{
                        "rule_trigger":"blind as a bat",
                        "lemma":"blind as a bat",
                        "word_type":"~a|||~n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma”:”Blind”,
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        },
                        "alternative_prio_2":{
                            "lemma":"((who is)) visually impaired",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma":"vision-impaired ((person))",
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1":"She was as blind as a bat when it came to understanding the complex math problem.",
                        "true_positive_sentence_2":"He was so blind as a bat that he couldn't even see the sign in front of him."
                    }
                    }
                    Translation:
                    {
                    "rule_category":"vision",
                    "rule_specification":{
                        "rule_trigger":"blind wie eine Fledermaus",
                        "lemma":"blind wie eine Fledermaus",
                        "word_type":"a||~|n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma":"schlecht sehen",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        },
                        "alternative_prio_2":{
                            "lemma":"mit schwachem Sehvermögen",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma":"",
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1":"Er war so blind wie eine Fledermaus, dass er das Schild vor ihm nicht sehen konnte.",
                        "true_positive_sentence_2":"Sie ist blind wie eine Fledermaus."
                    }
                    }

                    2. Sexual Orientation Category Example:
                    Original:
                    {
                    "rule_category":"sexual_orientation",
                    "rule_specification":{
                        "rule_trigger":"play for the other team",
                        "lemma":"play for the other team",
                        "word_type":"v|||a|n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma":"identify as lesbian",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        },
                        "alternative_prio_2":{
                            "lemma":"identify as gay",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma":"identify as a member of the LGBT+ community",
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1":"Does he play for the other team?",
                        "true_positive_sentence_2":",When you play for the other team, it means you are attracted to the same gender",
                    }
                    }
                    Translation: 
                    {
                    "rule_category":"sexual_orientation",
                    "rule_specification":{
                        "rule_trigger":"vom anderen Ufer",
                        "lemma":"vom anderen Ufer",
                        "word_type":"|a|n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma":"-",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        },
                        "alternative_prio_2":{
                            "lemma":"schwul",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma":"lesbisch",
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1":"Er ist vom anderen Ufer.”,
                        "true_positive_sentence_2":"Sie hat mir erzählt, dass sie vom anderen Ufer ist.”,
                    }
                    }

                    3. Titles Category example:
                    Original: 
                    {
                    "rule_category":"titles",
                    "rule_specification":{
                        "rule_trigger":"policeman",
                        "lemma":"policeman",
                        "word_type":"n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma”:”they”,
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        },
                        "alternative_prio_2":{
                            "lemma":"someone in the police",
                            "is_collective_noun":false,
                            "is_gendered_noun":false,
                            "is_advanced":false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma":"someone from the precinct",
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1":"The policeman stopped the car for speeding.",
                        "true_positive_sentence_2":"A policeman helped the lost child find her parents."
                    }
                    }
                    Translation: 
                    {
                    "rule_category":"titles",
                    "rule_specification":{
                        "rule_trigger":"Polizist",
                        "lemma":"Polizist",
                        "word_type":"n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma”:”~Polizist~”,
                            "is_collective_noun":false,
                            "is_gendered_noun”:true,
                            "is_advanced":false
                        },
                        "alternative_prio_2":{
                            "lemma":"~Polizei",
                            "is_collective_noun”:true,
                            "is_gendered_noun":false,
                            "is_advanced”:true
                        }
                    },
                    "alternative_prio_3":{
                        "lemma":"~Polizeikraft",
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1”:”Der Polizist hielt den Verkehr an, um den Kindern das sichere Überqueren der Straße zu ermöglichen."
                        "true_positive_sentence_2":"Im Krimi ermittelte der erfahrene Polizist geschickt und löste den Fall innerhalb von Tagen."
                    }
                    }
                    4. Gender Identity Category example:
                    Original: 
                    {
                    "rule_category":"gender_identity",
                    "rule_specification":{
                        "rule_trigger":"guys",
                        "lemma":"guys",
                        "word_type":"~n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma”:”team”,
                            "is_collective_noun”:true,
                            "is_gendered_noun”:false,
                            "is_advanced”:true
                        },
                        "alternative_prio_2":{
                            "lemma":"everyone",
                            "is_collective_noun”:true,
                            "is_gendered_noun":false,
                            "is_advanced”:false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma”:”folks”,
                        "is_collective_noun":false,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1”:”Hey guys, are you coming to the party tonight?"
                        "true_positive_sentence_2":"I told the guys that we need to leave early tomorrow."
                    }
                    }
                    Translation
                    {
                    "rule_category":"gender_identity",
                    "rule_specification":{
                        "rule_trigger”:”jungs”,
                        "lemma":"jungs",
                        "word_type":"~n"
                    },
                    "alternatives":{
                        "alternative_prio_1":{
                            "lemma”:”Leute”,
                            "is_collective_noun”:true,
                            "is_gendered_noun”:false,
                            "is_advanced”:true
                        },
                        "alternative_prio_2":{
                            "lemma”:”Alle”,
                            "is_collective_noun”:false,
                            "is_gendered_noun":false,
                            "is_advanced”:false
                        }
                    },
                    "alternative_prio_3":{
                        "lemma”:”Freunde”,
                        "is_collective_noun”:true,
                        "is_gendered_noun":false,
                        "is_advanced":false
                    },
                    "true_positive_examples":{
                        "true_positive_sentence_1”:”Hey Jungs, kommt ihr heute Abend zur Party?”,
                        "true_positive_sentence_2":"Ich habe den Jungs gesagt, dass wir morgen früh früh raus müssen."
                    }
                    }"""
        
                prompt=[        
                    {
                    "role": "system",
                    "content": instruction,
                    },
                {
                    "role": "user",
                    "content": "rule category information: " + dimension_info + "rule to translate: " + rule_formatted_for_translation
                },
                ]
                chat_completion = client.chat.completions.create(
                    model="gpt40125preview",
                    messages = prompt,
                    temperature=1.2,
                    max_tokens=500,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0
                )

                try:
                    # strip away everyting outside {}
                    result = chat_completion.choices[0].message.content
                    result = result[result.find("{"):result.rfind("}")+1]
                    print(f'result: {result}')


                    result_as_json = json.loads(result)
                    if 'rule_specification' not in result_as_json or 'alternatives' not in result_as_json:
                         raise ValueError("JSON structure is not as expected.")
                    
                    result_text_id = result_as_json['rule_specification']['rule_trigger']
                    result_lemma = result_as_json['rule_specification']['lemma']
                    result_word_types = result_as_json['rule_specification']['word_type']
                    result_alternatives_with_info = []

                    for i in range(1, 4):
                        alternative_key = f'alternative_prio_{i}'
                        if alternative_key in result_as_json['alternatives']:
                            #also check is_collective_noun, is_gendered_noun, is_advanced in the alternatives, if they are not, continue 
                            if 'lemma' not in result_as_json['alternatives'][alternative_key] or len(result_as_json['alternatives'][alternative_key]['lemma']) == 0 or 'is_collective_noun' not in result_as_json['alternatives'][alternative_key] or 'is_gendered_noun' not in result_as_json['alternatives'][alternative_key] or 'is_advanced' not in result_as_json['alternatives'][alternative_key]:
                                continue
                            result_alternatives_with_info.append({
                                "lemma": result_as_json['alternatives'][alternative_key]['lemma'],
                                "priority": i,
                                "is_collective_noun": result_as_json['alternatives'][alternative_key]['is_collective_noun'],
                                "is_gendered_noun": result_as_json['alternatives'][alternative_key]['is_gendered_noun'],
                                "is_advanced": result_as_json['alternatives'][alternative_key]['is_advanced']
                            })
                                                    
                    result_example_sentences = []
                    for i in range(1, 3):
                        if result_as_json['true_positive_examples'][f'true_positive_sentence_{i}'] != "":
                            result_example_sentences.append(result_as_json['true_positive_examples'][f'true_positive_sentence_{i}'])

                    current_date = date.today()
                    #add new rule to db
                    new_rule = Rule.objects.create(
                        text_id=result_text_id,
                        lemma=result_lemma,
                        word_types=result_word_types,
                        language="de",
                        is_active=False,
                        is_marked_for_review=True,
                        is_auto_generated=True,
                        generated_at=current_date,
                        source_rule=rule_formatted_for_translation,
                    )
                    new_rule.save()

                    #add RuleDiversityDimension
                    existing_diversity_dimension = DiversityDimension.objects.get(name=dimension_key)
                    new_rule_diversity_dimension = RuleDiversityDimension.objects.create(
                        rule=new_rule,
                        diversity_dimension=existing_diversity_dimension,
                        order=1
                    )
                    new_rule_diversity_dimension.save()                    

                    #add new alternatives to db
                    for i, alternative in enumerate(result_alternatives_with_info):
                        new_alternative = Alternative.objects.create(
                            rule=new_rule,
                            lemma=alternative['lemma'],
                            order=alternative['priority'],
                            is_collective_noun=alternative['is_collective_noun'],
                            is_gendered_noun=alternative['is_gendered_noun'],
                            is_advanced=alternative['is_advanced']
                        )
                        new_alternative.save()
                    
                    #add new example sentences to db
                    for i, example_sentence in enumerate(result_example_sentences):
                        #make sure is contains the rule trigger
                        if result_text_id not in example_sentence:
                            print(f"Skipping example sentence {example_sentence} because it doesn't contain the rule trigger")
                            continue

                        new_example_sentence = TrainingSentence.objects.create(
                            rule=new_rule,
                            text=example_sentence,
                            is_false_positive=False,
                            comment='auto generated'
                        )
                        new_example_sentence.save()
                    self.stdout.write(self.style.SUCCESS(f'added rule: {chat_completion.choices[0].message.content}'))

                except Exception as e:
                    logger.error(f"Error processing rule: {e}")   
                    with open('rules/management/commands/translated_rules_error.json', 'a') as file:
                        file.write('Error: ' + str(e) + '\n')
                        file.write('Rule: ' + str(rule) + '\n')  
                        file.write('Result: ' + str(result) + '\n')        
            except Exception as e:
                # Log the error and skip to the next rule
                logger.error(f"Error processing rule {rule.id}: {e}")
                continue  # Move to the next iteration

