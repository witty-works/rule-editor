from django.core.management.base import BaseCommand
from rules.models import Rule, TrainingSentence
from django.conf import settings
from openai import AzureOpenAI
import json


class Command(BaseCommand):
    help = "Generates additional training sentences for rules"

    def handle(self, *args, **options):
        instruction = """You are a sentence generator for inclusive language rules.
        You take a rule word or phrase as input and output sentences that contain that word or phrase in a way that should trigger the rule.
        Examples of complete jsons can be seen below."""

        examples = """{
            "example_long_de":{
                "rule_specification":{
                    "rule_trigger":"vom anderen Ufer",
                    "lemma":"vom anderen Ufer",
                    "word_type":"|a|n"
                },
                "true_positive_examples":{
                    "true_positive_sentence_1":"Wir haben uns gestern getroffen und er hat mir erzählt, dass er vom anderen Ufer ist.",
                    "true_positive_sentence_2":"Hast du schon gehört, dass er vom anderen Ufer ist?"
                }
            },
            "example_long_en":{
                "rule_specification":{
                    "rule_trigger":"blind as a bat",
                    "lemma":"blind as a bat",
                    "word_type":"~a|||~n"
                },
                "true_positive_examples":{
                    "true_positive_sentence_1":"She was as blind as a bat when it came to understanding the complex math problem.",
                    "true_positive_sentence_2":"He was so blind as a bat that he couldn't even see the sign in front of him."
                }
            },
            "example_short_de":{
                "rule_specification":{
                    "rule_trigger":"Chef",
                    "lemma":"Chef",
                    "word_type":"n"
                },
                "true_positive_examples":{
                    "true_positive_sentence_1":"Der Chef hat die Entscheidung getroffen.",
                    "true_positive_sentence_2":"Er ist der Chef des Unternehmens."
                }
            },
            "example_short_en":{
                "rule_specification":{
                    "rule_trigger":"landlady",
                    "lemma":"landlady",
                    "word_type":"n"
                },
                "true_positive_examples":{
                    "true_positive_sentence_1":"She is the landlady of the building.",
                    "true_positive_sentence_2":"The landlady is very kind."
                }
            }
        }"""
        trigger = "Complete the empty sentence fields in the last json. Return only the complete json."

        client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_KEY,
            api_version=settings.AZURE_OPENAI_VERSION,
        )
        rules = Rule.objects.filter(language="en")
        for rule in rules:
            try:
                training_sentences = TrainingSentence.objects.filter(
                    rule=rule, is_false_positive=0
                )
                if len(training_sentences) < 2:
                    formatted_rule_for_generation = f"""{{
                        "rule_specification":{{
                            "rule_trigger":"{rule.text_id}",
                            "lemma":"{rule.lemma}",
                            "word_type":"{rule.word_types}"
                        }},
                        "true_positive_examples":{{
                            "true_positive_sentence_1":"",
                            "true_positive_sentence_2":""
                        }},
                    }}"""
                    prompt = [
                        {
                            "role": "system",
                            "content": instruction
                            + examples
                            + formatted_rule_for_generation
                            + trigger,
                        }
                    ]
                    chat_completion = client.chat.completions.create(
                        model=settings.AZURE_OPENAI_MODEL,
                        messages=prompt,
                        temperature=0.8,
                        max_tokens=800,
                        top_p=0.95,
                        frequency_penalty=0,
                        presence_penalty=0,
                        stop=None,
                    )
                    print(
                        f"chat_completion: {chat_completion.choices[0].message.content}"
                    )
                    api_response = json.loads(
                        chat_completion.choices[0].message.content
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"Generated sentences: {api_response}")
                    )

                    tp_sentences = api_response["true_positive_examples"].values()

                    if tp_sentences.startswith("I'm sorry"):
                        self.stdout.write(
                            self.style.ERROR(
                                f"Failed to generate sentences for rule: {rule}. Error: {tp_sentences}"
                            )
                        )
                        continue

                    for sentence in tp_sentences:
                        if sentence:  # Ensure the sentence is not empty
                            TrainingSentence.objects.create(
                                rule=rule,
                                text=sentence,
                                is_false_positive=False,
                                comment="auto generated",
                            )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Generated additional training sentences for rule: {rule}"
                        )
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to generate sentences for rule: {rule}. Error: {e}"
                    )
                )
                continue
