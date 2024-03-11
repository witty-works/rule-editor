from django.core.management.base import BaseCommand
from rules.models import Rule, TrainingSentence, Alternative

class Command(BaseCommand):
    help = (
        "Translates english rules into german and saves them in the database."
    )

    def handle(self, *args, **options):
        rules = Rule.objects.all()
        base_prompt = "You are an inclusive rule translator. Your input is a JSON object containing rule specifications. Your goal is to translate these rules into German. The translation may be direct or adapted to better suit cultural or linguistic nuances. Below, you will find examples of correct translations, alongside and an explanation of the rule category the target rule belongs to."

        example_translations = {
                "example_long_direct_en":{
                    "rule_category":"vision", 
                    "rule_specification":{
                        "rule_trigger":"blind as a bat", 
                        "lemma":"blind as a bat",
                        "word_type": "~a|||~n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"blind",
                        "alternative_prio_2":"vision impaired person",
                        "alternative_prio_3":"person who is blind"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"She was as blind as a bat when it came to understanding the complex math problem.",
                        "true_positive_sentence_2":"He was so blind as a bat that he couldn't even see the sign in front of him."
                    }
                },
                "example_long_direct_de": {
                    "rule_category":"vision", 
                        "rule_specification":{
                        "rule_trigger":"blind wie eine Fledermaus", 
                        "lemma":"blind wie eine Fledermaus",
                        "word_type": "a||~|n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"schlecht sehen",
                        "alternative_prio_2":"mit schwachem Sehvermögen",
                        "alternative_prio_3":""
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Er war so blind wie eine Fledermaus, dass er das Schild vor ihm nicht sehen konnte.",
                        "true_positive_sentence_2":"Sie ist blind wie eine Fledermaus."
                    }
                }, 
                "example_long_non_direct_en": {
                    "rule_category":"sexual_orientation", 
                    "rule_specification":{
                        "rule_trigger":"play for the other team", 
                        "lemma":"play for the other team",
                        "word_type": "v|||a|n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"identify as lesbian",
                        "alternative_prio_2":"identify as gay",
                        "alternative_prio_3":"identify as a member of the LGBT+ community"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Does he play for the other team?",
                        "true_positive_sentence_2":"She plays for the other team."
                    }
                },
                "example_long_non_direct_de:": {
                    "rule_category":"sexual_orientation", 
                    "rule_specification":{
                        "rule_trigger":"vom anderen Ufer", 
                        "lemma":"vom anderen Ufer",
                        "word_type": "|a|n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"[REMOVE]",
                        "alternative_prio_2":"schwul",
                        "alternative_prio_3":"lesbisch"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Er ist vom anderen Ufer.",
                        "true_positive_sentence_2":"Sie hat mir erzählt, dass sie vom anderen Ufer ist."
                    },
                }, 
                "example_short_direct_en": {
                    "rule_category":"leadership", 
                    "rule_specification":{
                        "rule_trigger":"boss", 
                        "lemma":"boss",
                        "word_type": "n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"management",
                        "alternative_prio_2":"administration",
                        "alternative_prio_3":"supervisor"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"I'll have to ask my boss about this decision.",
                        "true_positive_sentence_2":"The boss is always right."
                    }
                }, 
                "example_short_direct_de": {
                    "rule_category":"leadership", 
                    "rule_specification":{
                        "rule_trigger":"Chef", 
                        "lemma":"Chef",
                        "word_type": "n",
                        "lemma_type":"suffix", 
                        "entity_type":"non_person",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"Leitungsperson",
                        "alternative_prio_2":"CEOs",
                        "alternative_prio_3":"verantwortliche Person"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Der Chef hat die Entscheidung getroffen.",
                        "true_positive_sentence_2":"Er ist der Chef des Unternehmens."
                    }
                }
            }
        # TODO: add   # "example_short_non_direct_en": {
                # },
                # "example_short_non_direct_de": {
                # }    
        

        for rule in rules:
            if rule.language != "en":
                continue

            alternatives = Alternative.objects.filter(rule_id=rule.id, is_inspiration=0)
            example_sentences = TrainingSentence.objects.filter(rule=rule)
            true_positive_sentences = example_sentences.filter(is_false_positive=False)
            false_positive_sentences = example_sentences.filter(is_false_positive=True)

            #if no alternatives or example sentences, skip rule
            if (len(alternatives) == 0) or (len(true_positive_sentences) == 0) or (len(false_positive_sentences) == 0):
                # self.stdout.write(self.style.ERROR(f"Skipping rule {rule} because it has no alternatives or example sentences"))
                continue

            self.stdout.write(self.style.WARNING(f"Translating rule {rule}"))
            rule_formatted_for_translation = {
                "rule_category": rule.diversity_dimension_json[0],
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
                    "true_positive_sentence_1": true_positive_sentences[0].text if len(true_positive_sentences) > 0 else "",
                    "true_positive_sentence_2": true_positive_sentences[1].text if len(true_positive_sentences) > 1 else ""
                },
            }
            self.stdout.write(self.style.SUCCESS(f"Translating rule {rule}"))
    
            # prompt = base_prompt + example_translation_categories + example_translations + rule_formatted_for_translation_category + rule_formatted_for_translation
            prompt = base_prompt + example_translations + rule_formatted_for_translation


           

                


