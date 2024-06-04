from django.core.management.base import BaseCommand
from rules.models import (
    DiversityDimension,
    Rule,
    RuleDiversityDimension,
    TrainingSentence,
    Alternative,
)
from openai import AzureOpenAI
from os import environ
import json
import logging
from datetime import date

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Translates english rules into german or french and saves them in the database."
    )

    def handle(self, *args, **options):
        try:
            rules = Rule.objects.all().filter(language="en")
        except Exception as e:
            logger.error(f"Failed to fetch rules: {e}")
            return

        try:
            with open(
                "rules/management/commands/diversity_dimensions.json", "r"
            ) as file:
                all_diversity_dimensions = json.load(file)
        except Exception as e:
            logger.error(f"Failed to load diversity dimensions: {e}")
            return

        client = AzureOpenAI(
            azure_endpoint=environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=environ.get("AZURE_OPENAI_KEY"),
            api_version=environ.get("AZURE_OPENAI_VERSION"),
        )
        rules_generated = 0
        instruction = ""
        with open(
            "rules/management/commands/translation_prompt_en_de.txt", "r"
        ) as file:  # CHANGE THIS TO WITCH BETWEEN LANGUAGES
            instruction = file.read()
        for rule in rules.order_by("?"):  # Randomize the order of rules
            try:
                alternatives = rule.alternatives.all()
                example_sentences = rule.training_sentences.all()

                # if no alternatives skip rule
                if len(alternatives) == 0:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Skipping rule {rule} because it has no alternatives"
                        )
                    )
                    continue

                dimension_key = rule.diversity_dimension_json[0].removesuffix(
                    "_advanced"
                )

                dimension_info = all_diversity_dimensions[dimension_key]
                dimension_info = str(dimension_info).replace("'", '"')
                rule_formatted_for_translation = {
                    "rule_category": dimension_key,
                    "rule_specification": {
                        "rule_trigger": rule.text_id,
                        "lemma": rule.lemma,
                        "word_type": rule.word_types,
                    },
                    "alternatives": {},
                    "true_positive_examples": {},
                }

                for i in range(1, 4):
                    key = f"alternative_prio_{i}"
                    if len(alternatives) >= i:
                        alt = alternatives[i - 1]
                        rule_formatted_for_translation["alternatives"][key] = {
                            "lemma": alt.lemma,
                            "is_collective_noun": alt.is_collective_noun,
                            "is_gendered_noun": alt.is_gendered_noun,
                            "is_advanced": alt.is_advanced,
                            "is_remove": alt.is_remove,
                        }
                    else:
                        rule_formatted_for_translation["alternatives"][key] = {
                            "lemma": "",
                            "is_collective_noun": False,
                            "is_gendered_noun": False,
                            "is_advanced": False,
                            "is_remove": False,
                        }

                # Dynamically fill the true_positive_examples section
                for i in range(1, 3):  # Assuming we need up to 2 true positive examples
                    key = f"true_positive_sentence_{i}"
                    if len(example_sentences) >= i:
                        rule_formatted_for_translation["true_positive_examples"][
                            key
                        ] = example_sentences[i - 1].text
                    else:
                        rule_formatted_for_translation["true_positive_examples"][
                            key
                        ] = ""

                rule_formatted_for_translation = json.dumps(
                    rule_formatted_for_translation, indent=2
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Translating rule: {rule_formatted_for_translation}"
                    )
                )
                prompt = [
                    {
                        "role": "system",
                        "content": instruction,
                    },
                    {
                        "role": "user",
                        "content": "rule category information: "
                        + dimension_info
                        + "rule to translate: "
                        + rule_formatted_for_translation,
                    },
                ]
                chat_completion = client.chat.completions.create(
                    model="gpt40125preview",
                    messages=prompt,
                    temperature=1.2,
                    max_tokens=800,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                )

                try:
                    # strip away everyting outside {}
                    result = chat_completion.choices[0].message.content
                    result = result[result.find("{") : result.rfind("}") + 1]

                    result_as_json = json.loads(result)
                    if (
                        "rule_specification" not in result_as_json
                        or "alternatives" not in result_as_json
                    ):
                        raise ValueError("JSON structure is not as expected.")

                    result_text_id = result_as_json["rule_specification"][
                        "rule_trigger"
                    ]
                    result_lemma = result_as_json["rule_specification"]["lemma"]
                    result_word_types = result_as_json["rule_specification"][
                        "word_type"
                    ]
                    result_alternatives_with_info = []

                    for i in range(1, 4):
                        alternative_key = f"alternative_prio_{i}"
                        if (
                            alternative_key in result_as_json["alternatives"]
                            and "lemma"
                            in result_as_json["alternatives"][alternative_key]
                            and len(
                                result_as_json["alternatives"][alternative_key]["lemma"]
                            )
                            > 0
                            and "is_collective_noun"
                            in result_as_json["alternatives"][alternative_key]
                            and "is_gendered_noun"
                            in result_as_json["alternatives"][alternative_key]
                            and "is_advanced"
                            in result_as_json["alternatives"][alternative_key]
                            and "is_remove"
                            in result_as_json["alternatives"][alternative_key]
                        ):
                            result_alternatives_with_info.append(
                                {
                                    "lemma": result_as_json["alternatives"][
                                        alternative_key
                                    ]["lemma"],
                                    "priority": i,
                                    "is_collective_noun": result_as_json[
                                        "alternatives"
                                    ][alternative_key]["is_collective_noun"],
                                    "is_gendered_noun": result_as_json["alternatives"][
                                        alternative_key
                                    ]["is_gendered_noun"],
                                    "is_advanced": result_as_json["alternatives"][
                                        alternative_key
                                    ]["is_advanced"],
                                    "is_remove": result_as_json["alternatives"][
                                        alternative_key
                                    ]["is_remove"],
                                }
                            )

                    result_example_sentences = []
                    for i in range(1, 3):
                        if (
                            result_as_json["true_positive_examples"][
                                f"true_positive_sentence_{i}"
                            ]
                            != ""
                        ):
                            result_example_sentences.append(
                                result_as_json["true_positive_examples"][
                                    f"true_positive_sentence_{i}"
                                ]
                            )

                    current_date = date.today()
                    # add new rule to db
                    new_rule = Rule.objects.create(
                        text_id=result_text_id,
                        lemma=result_lemma,
                        word_types=result_word_types,
                        language="de",  # REMEMBER TO CHANGE THIS WHEN CHANGING LANGUAGE
                        is_active=False,
                        is_marked_for_review=True,
                        is_auto_generated=True,
                        generated_at=current_date,
                        source_rule=rule_formatted_for_translation,
                        rule_translation_source=rule,
                    )
                    new_rule.save()
                    rules_generated += 1

                    # add RuleDiversityDimension
                    existing_diversity_dimension = DiversityDimension.objects.get(
                        name=dimension_key
                    )
                    new_rule_diversity_dimension = (
                        RuleDiversityDimension.objects.create(
                            rule=new_rule,
                            diversity_dimension=existing_diversity_dimension,
                            order=1,
                        )
                    )
                    new_rule_diversity_dimension.save()
                    # add new alternatives to db
                    for i, alternative in enumerate(result_alternatives_with_info):
                        new_alternative = Alternative.objects.create(
                            rule=new_rule,
                            lemma=alternative["lemma"],
                            order=alternative["priority"],
                            is_collective_noun=alternative["is_collective_noun"],
                            is_gendered_noun=alternative["is_gendered_noun"],
                            is_advanced=alternative["is_advanced"],
                            is_remove=alternative["is_remove"],
                        )
                        new_alternative.save()

                    # add new example sentences to db
                    for i, example_sentence in enumerate(result_example_sentences):
                        if result_text_id not in example_sentence:
                            print(
                                f"Skipping example sentence {example_sentence} because it doesn't contain the rule trigger"
                            )
                            continue

                        new_example_sentence = TrainingSentence.objects.create(
                            rule=new_rule,
                            text=example_sentence,
                            is_false_positive=False,
                            comment="auto generated",
                        )
                        new_example_sentence.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"added rule (nr): {rules_generated, chat_completion.choices[0].message.content}"
                        )
                    )
                    if rules_generated >= 100:
                        break
                except Exception as e:
                    logger.error(f"Error processing rule: {e}")
                    with open(
                        "rules/management/commands/translated_rules_error_de.json", "a"
                    ) as file:  # REMOVE THIS AFTER INITIAL RULE GENERATION
                        file.write("Error: " + str(e) + "\n")
                        file.write("Rule: " + str(rule) + "\n")
                        file.write("Result: " + str(result) + "\n")
            except Exception as e:
                # Log the error and skip to the next rule
                logger.error(f"Error processing rule {rule.id}: {e}")
                continue  # Move to the next iteration
