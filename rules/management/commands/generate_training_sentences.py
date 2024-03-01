from django.core.management.base import BaseCommand
from rules.models import Rule, TrainingSentence
from openai import OpenAI
from os import environ
import json

class Command(BaseCommand):
    help = "Generates additional training sentences for rules"    
    
    def handle(self, *args, **options):
        #COULD ADD DIVERSITY DIMENSION INFORMATION
        instruciton = """You are a true positive and false positive sentence generator for inclusive language rules.
        You take a rule word or phrase as input and output sentences that contain that word or phrase in a way that should be triggered (TP) and in a way that should not be triggered (FP).
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
                },
                "false_positive_examples":{
                    "false_positive_sentence_1":"Beim Segeln sprach er von einer Insel 'vom anderen Ufer', die wir besuchen sollten, weit entfernt von unserem aktuellen Standort",
                    "false_positive_sentence_2":"In ihrer Geschichte beschreibt die Autorin eine geheimnisvolle Figur 'vom anderen Ufer', die symbolisch für Veränderung und das Unbekannte steht."
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
                },
                "false_positive_examples":{
                    "false_positive_sentence_1":"In her biology presentation, she explained that bats are not actually blind, debunking the myth of being 'blind as a bat'.",
                    "false_positive_sentence_2":""
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
                },
                "false_positive_examples":{
                    "false_positive_sentence_1":"Er ist Chefkoch in einem renommierten Restaurant",
                    "false_positive_sentence_2":"In der Fernsehshow ist er als Chefjuror bekannt."
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
                },
                "false_positive_examples":{
                    "false_positive_sentence_1":"In her novel, the author describes a character as a 'landlady' to capture the historical setting accurately.",
                    "false_positive_sentence_2":"The discussion on gender roles in 19th-century property ownership highlighted the role of the 'landlady' in literature and society."
                }
            }
        }"""
        trigger =  "Complete the empty sentence fields in the last json. Return only the complete json."
        
        API_KEY = environ.get('GPT_API_KEY_SOLVEIG')
        openai = OpenAI(api_key=API_KEY)

        rules = Rule.objects.all()
        for rule in rules[:1]:
            training_sentences = TrainingSentence.objects.filter(rule=rule)
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
                    "false_positive_examples":{{
                        "false_positive_sentence_1":"",
                        "false_positive_sentence_2":""
                    }}
                }}"""
                prompt = instruciton + examples + formatted_rule_for_generation + trigger

                chat_completion = openai.chat.completions.create(
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    model="gpt-4-1106-preview",
                    temperature=0.8,
                )
                api_response = json.loads(chat_completion.choices[0].message.content)
                print(api_response)

                tp_sentences = api_response["true_positive_examples"].values()
                fp_sentences = api_response["false_positive_examples"].values()
                    
                for sentence in tp_sentences:
                    if sentence:  # Ensure the sentence is not empty
                        TrainingSentence.objects.create(
                            rule=rule,
                            text=sentence,
                            is_false_positive=False,
                            comment='auto generated'
                        )
                for sentence in fp_sentences:
                    if sentence:  # Ensure the sentence is not empty
                        TrainingSentence.objects.create(
                            rule=rule,
                            text=sentence,
                            is_false_positive=True,
                            comment='auto generated'
                        )
    
                self.stdout.write(self.style.SUCCESS(f'Generated additional training sentences for rule: {rule}'))
                    


