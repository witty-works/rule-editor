from django.core.management.base import BaseCommand
from rules.models import (
    Rule,
    Alternative,
    FalsePositive,
    TrainingSentence,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
    RuleTypeEnum,
    RuleLabelEnum,
    AlternativeTypeEnum,
    AlternativePluralizationEnum,
    EnglishVerb,
    EnglishAdjective,
    EnglishNoun,
    GermanVerb,
    GermanAdjective,
    GermanNoun,
)
import csv
import re
from inflex import Noun, Verb, Adjective


class Command(BaseCommand):
    help = "Imports or updates rules"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)
        parser.add_argument("--language", type=str)
        parser.add_argument("--skip", type=bool, default=False)

    def handle_lemmas(self, language, tokens: [], word_types: []):
        if word_types is None:
            return

        for i in range(len(word_types)):
            if not word_types[i]["lemmatize"]:
                continue

            if "v" in word_types[i]["word_type"]:
                if language == "de":
                    try:
                        GermanVerb.objects.get(base_form=tokens[i])
                    except GermanVerb.DoesNotExist:
                        verb = GermanVerb()
                        verb.base_form = tokens[i]
                        verb.save()
                else:
                    inflex = Verb(tokens[i])
                    try:
                        EnglishVerb.objects.get(base_form=tokens[i])
                    except EnglishVerb.DoesNotExist:
                        verb = EnglishVerb()
                        verb.base_form = tokens[i]
                        verb.past_tense = inflex.past()
                        verb.past_participle = inflex.past_part()
                        verb.present_participle = inflex.pres_part()
                        verb.third_person_singular = inflex.singular()
                        verb.save()

                        self.stdout.write(self.style.SUCCESS(f"Verb added {tokens[i]}"))

            if "a" in word_types[i]["word_type"]:
                if language == "de":
                    try:
                        GermanAdjective.objects.get(base_form=tokens[i])
                    except GermanAdjective.DoesNotExist:
                        verb = GermanAdjective()
                        verb.base_form = tokens[i]
                        verb.save()
                else:
                    inflex = Adjective(tokens[i])
                    try:
                        EnglishAdjective.objects.get(base_form=tokens[i])
                    except EnglishAdjective.DoesNotExist:
                        adjective = EnglishAdjective()
                        adjective.base_form = tokens[i]
                        if tokens[i].isupper():
                            adjective.comparative = tokens[i]
                            adjective.superlative = tokens[i]
                        else:
                            adjective.comparative = inflex.comparative()
                            adjective.superlative = inflex.superlative()
                        adjective.save()

                        self.stdout.write(
                            self.style.SUCCESS(f"Adjective added {tokens[i]}")
                        )

            # BC code "s"
            if "s" in word_types[i]["word_type"] and "n" in word_types[i]["word_type"]:
                if language == "de":
                    try:
                        GermanNoun.objects.get(base_form=tokens[i])
                    except GermanNoun.DoesNotExist:
                        verb = GermanNoun()
                        verb.base_form = tokens[i]
                        verb.save()
                else:
                    inflex = Noun(tokens[i])
                    try:
                        EnglishNoun.objects.get(base_form=tokens[i])
                    except EnglishNoun.DoesNotExist:
                        noun = EnglishNoun()
                        noun.base_form = tokens[i]
                        noun.plural = inflex.plural()
                        noun.save()

                        self.stdout.write(self.style.SUCCESS(f"Noun added {tokens[i]}"))

    def handle(self, *args, **options):
        language = options["language"]

        with open(options["file"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                lemma = row["Lemma"].strip()
                if len(lemma) == 0:
                    continue

                # BC code "s" -> "n"
                word_types = row["Word_Type"].strip().replace("s", "n")

                self.stdout.write(
                    self.style.NOTICE(f"Processing lemma '{lemma}' / '{word_types}'")
                )

                try:
                    rule = Rule.objects.get(
                        lemma=lemma, word_types=word_types, language=language
                    )
                    if options["skip"]:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"Skipping lemma '{lemma}' / '{word_types}'"
                            )
                        )
                        continue
                    message = f"Successfully updated rule '{lemma}' / '{word_types}'"

                    RuleDiversityDimension.objects.filter(rule=rule).delete()
                    Alternative.objects.filter(rule=rule).delete()
                    FalsePositive.objects.filter(rule=rule).delete()
                    TrainingSentence.objects.filter(rule=rule).delete()
                    for tag in rule.tags.all():
                        tag.delete()
                except Rule.DoesNotExist:
                    rule = Rule()
                    rule.lemma = lemma
                    rule.word_types = word_types
                    rule.language = language
                    message = f"Successfully created rule '{lemma}' / '{word_types}'"

                rule.text_id = lemma
                rule.type = RuleTypeEnum.DEFAULT
                rule.is_context_aware = lemma in [
                    "fossil",
                    "flexible",
                    "impact",
                    "dynamic",
                    "best",
                    "alone",
                    "retarded",
                    "brilliant",
                    "retard",
                ]
                rule.is_marked_for_review = True

                # 3rd_party_alternatives,Notes,ToClarify
                if row["Notes"] is not None:
                    rule.comment = row["Notes"].strip()
                if (
                    row["3rd_party_alternatives"] is not None
                    and row["3rd_party_alternatives"].strip()
                ):
                    rule.comment += (
                        "\n3rd_party_alternatives:\n"
                        + row["3rd_party_alternatives"].strip()
                    )
                if row["ToClarify"] is not None and row["ToClarify"].strip():
                    rule.comment += "\ToClarify:\n" + row["ToClarify"].strip()

                # 3rd_party_source
                source_name = row["3rd_party_source"].strip()
                if len(source_name):
                    try:
                        source = Source.objects.get(name=source_name)
                    except Source.DoesNotExist:
                        source = Source()
                        source.name = source_name
                        source.save()

                    rule.source = source

                rule.save()

                self.handle_lemmas(language, rule.tokenized, rule.parse_word_types())

                priorties = [s.strip() for s in row["Priority"].split("|")]
                if "HR" in priorties:
                    rule.tags.add("hr")

                is_basic = (
                    "basic" in priorties or row["Category"] == "openly_discriminating"
                )
                self.add_diversity_dimension(
                    rule, row["Primary_subcategory"], 0, is_basic
                )

                if (
                    row["Secondary_subcategory"]
                    and row["Secondary_subcategory"] != "generic_plural"
                ):
                    self.add_diversity_dimension(
                        rule, row["Secondary_subcategory"], 1, is_basic
                    )

                alternative_columns = {
                    "Alt_Sg_Replacement": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.DEFAULT,
                        "word_types": True,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Field": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.DEFAULT,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Sg_/_and_inclusive_form": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.SINGULAR_ONLY,
                        "word_types": True,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Medical_term": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.DEFAULT,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Identity_first": {
                        "type": AlternativeTypeEnum.IDENTITY_FIRST,
                        "pluralization": AlternativePluralizationEnum.SINGULAR_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Sg_people_first": {
                        "type": AlternativeTypeEnum.PERSON_FIRST,
                        "pluralization": AlternativePluralizationEnum.SINGULAR_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Sg_reframed": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.DEFAULT,
                        "word_types": False,
                        "is_inspiration": True,
                        "is_advanced": False,
                    },
                    "Alt_Pl_pair_and_inclusive_form": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.PLURAL_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Pl_collective_noun": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.PLURAL_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Pl": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.PLURAL_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Identity_first_pl": {
                        "type": AlternativeTypeEnum.IDENTITY_FIRST,
                        "pluralization": AlternativePluralizationEnum.PLURAL_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Pl_people_first": {
                        "type": AlternativeTypeEnum.PERSON_FIRST,
                        "pluralization": AlternativePluralizationEnum.PLURAL_ONLY,
                        "word_types": False,
                        "is_inspiration": False,
                        "is_advanced": False,
                    },
                    "Alt_Pl_reframed": {
                        "type": AlternativeTypeEnum.DEFAULT,
                        "pluralization": AlternativePluralizationEnum.PLURAL_ONLY,
                        "word_types": False,
                        "is_inspiration": True,
                        "is_advanced": False,
                    },
                }

                label_types = {
                    "be specific to build trust": RuleLabelEnum.BE_SPECIFIC,
                    "Describe the specific concern": RuleLabelEnum.BE_SPECIFIC,
                    "Try not to use this word to describe people": RuleLabelEnum.NOT_FOR_PEOPLE,
                    "Don't use this word for people": RuleLabelEnum.NOT_FOR_PEOPLE,
                    "Name the disability or condition": RuleLabelEnum.NAME_DISABILITY,
                    "Only if gender identity is relevant": RuleLabelEnum.ONLY_IF_GENDER_IDENTITY_RELEVANT,
                    "Only if self-identifies as female": RuleLabelEnum.ONLY_IF_GENDER_IDENTITY_RELEVANT,
                    "Don't use in a non-combat context": RuleLabelEnum.NOT_FOR_NON_COMBAT,
                    "if stated preference": RuleLabelEnum.ASK_FOR_PREFERENCE,
                    "Only use in reference to religious practice": RuleLabelEnum.ONLY_WHEN_REFERENCING_RELIGIOUS_PRACTICE,
                    "Use in programming only": RuleLabelEnum.USE_IN_TECH_ONLY,
                    "Don't use to describe value or quality": RuleLabelEnum.DONT_USE_TO_DESCRIBE_QUALITY,
                    "Don't use in the context of substance use": RuleLabelEnum.DONT_USE_FOR_SUBSTANCE_USE,
                    "Ask about their traditions, if possible": RuleLabelEnum.ASK_ABOUT_TRADITIONS,
                    "Nicht zum Beschreiben von Personen": RuleLabelEnum.NOT_FOR_PEOPLE,
                    "nicht auf Menschen beziehen": RuleLabelEnum.NOT_FOR_PEOPLE,
                    "nur erwähnen, wenn relevant": RuleLabelEnum.ONLY_IF_GENDER_IDENTITY_RELEVANT,
                    "nur wenn die Person sich selbst so bezeichnet": RuleLabelEnum.ASK_FOR_PREFERENCE,
                    "nur wenn die Person sich so bezeichnet": RuleLabelEnum.ASK_FOR_PREFERENCE,
                    "Kultur nennen": RuleLabelEnum.BE_SPECIFIC,
                    "Region oder Land nennen": RuleLabelEnum.BE_SPECIFIC,
                    "Nationalität nennen": RuleLabelEnum.BE_SPECIFIC,
                    "Länder nennen": RuleLabelEnum.BE_SPECIFIC,
                    "Sprache nennen": RuleLabelEnum.BE_SPECIFIC,
                    "nicht für Einzelperson": RuleLabelEnum.DEFAULT,
                    "nicht für Menschen mit Behinderungen": RuleLabelEnum.DEFAULT,
                    "nicht für den Alltag von Menschen mit Behinderungen": RuleLabelEnum.DEFAULT,
                    "lieber relevante Fähigkeiten nennen": RuleLabelEnum.DEFAULT,
                    "nur im rechtlichen oder religiösen Kontext": RuleLabelEnum.DEFAULT,
                    "nicht für Menschen oder ihr Handeln": RuleLabelEnum.DEFAULT,
                    "nicht für Mitmenschen verwenden": RuleLabelEnum.DEFAULT,
                    "nur für Menschenschmuggel aus Profitstreben": RuleLabelEnum.DEFAULT,
                    "indigene Gruppe nennen": RuleLabelEnum.DEFAULT,
                }

                rule_tokens, rule_lemmas = rule.tokenize()
                rule.label_type = RuleLabelEnum.DEFAULT
                rule.label = None

                alternative_count = 0
                for alternative_column in alternative_columns:
                    alternative_column_count = 0
                    if alternative_column not in row:
                        self.stdout.write(
                            self.style.NOTICE(f"Column missing {alternative_column}")
                        )
                        continue

                    alternatives = row[alternative_column].strip()
                    alternatives = alternatives.split("|")
                    if len(alternatives) == 0:
                        continue

                    for alternative_lemma in alternatives:
                        if alternative_lemma.startswith("---"):
                            rule.label = alternative_lemma.removeprefix("---").strip()
                            rule.label_type = (
                                label_types[rule.label]
                                if label in label_types
                                else RuleLabelEnum.DEFAULT
                            )

                            continue

                        if " --- " in alternative_lemma:
                            alternative_lemma, label = alternative_lemma.split(" --- ")
                            label = label.strip()
                        else:
                            label = None

                        alternative_lemma = alternative_lemma.strip()

                        if len(alternative_lemma) == 0:
                            continue

                        alternative = Alternative()
                        alternative.rule = rule
                        alternative.lemma = alternative_lemma
                        alternative.comment = (
                            f"{alternative_column} {alternative_column_count}"
                        )
                        alternative_column_count += 1

                        if alternative_lemma == "-":
                            alternative.is_remove = True

                        if alternative_columns[alternative_column]["word_types"]:
                            (
                                alternative_rule_tokens,
                                alternative_rule_lemmas,
                            ) = alternative.tokenize()
                            if len(rule_tokens) == len(alternative_rule_tokens):
                                alternative.word_types = rule.word_types
                                self.handle_lemmas(
                                    language,
                                    alternative_rule_tokens,
                                    alternative.parse_word_types(),
                                )

                        alternative.label = label
                        alternative.type = alternative_columns[alternative_column][
                            "type"
                        ]
                        alternative.pluralization = alternative_columns[
                            alternative_column
                        ]["pluralization"]
                        if "..." in alternative.lemma or (
                            "(" in alternative.lemma
                            and ")" in alternative.lemma
                            and "((" not in alternative.lemma
                            and "))" not in alternative.lemma
                            and "abbreviation" not in row["Primary_subcategory"]
                        ):
                            alternative.is_inspiration = True
                        else:
                            alternative.is_inspiration = alternative_columns[
                                alternative_column
                            ]["is_inspiration"]
                        alternative.is_advanced = alternative_columns[
                            alternative_column
                        ]["is_advanced"]

                        alternative.order = alternative_count
                        alternative.save()
                        alternative_count += 1

                if alternative_count == 0 and row["Category"] == "inclusive":
                    alternative = Alternative()
                    alternative.rule = rule
                    alternative.lemma = "-"
                    alternative.word_types = ""
                    alternative.order = 0
                    alternative.is_remove = True
                    alternative.comment = "Rule had no alternatives"
                    alternative.save()
                    self.stdout.write(
                        self.style.NOTICE(f"Added implicit remove alternative")
                    )
                else:
                    self.stdout.write(
                        self.style.NOTICE(f"Added {alternative_count} alternatives")
                    )

                # False_Positives
                false_positives = row["False_Positives"].strip()
                false_positives = false_positives.split("|")
                false_positive_texts = []
                for false_positive_text in false_positives:
                    false_positive_text = false_positive_text.strip()
                    if (
                        len(false_positive_text) == 0
                        or false_positive_text in false_positive_texts
                    ):
                        continue

                    false_positive_texts.append(false_positive_text)

                    false_positive = FalsePositive()
                    false_positive.rule = rule
                    false_positive.false_positive = false_positive_text
                    false_positive.save()

                # Sample_Sentences,Generated Examples
                training_sentences_columns = [
                    "Sample_Sentences",
                    "Generated Examples",
                ]
                for training_sentences_column in training_sentences_columns:
                    if training_sentences_column not in row:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"Column missing {training_sentences_column}"
                            )
                        )
                        continue

                    if row[training_sentences_column] is None:
                        continue

                    training_sentences = row[training_sentences_column].strip()
                    training_sentences = training_sentences.replace("|", "\n")
                    training_sentences = training_sentences.split("\n")

                    for training_sentence_text in training_sentences:
                        training_sentence_text = training_sentence_text.strip()
                        if len(training_sentence_text) == 0:
                            continue

                        x = re.search("\d+\. (.+)", training_sentence_text)
                        if x:
                            training_sentence_text = x.group(1)

                        training_sentence = TrainingSentence()
                        training_sentence.rule = rule
                        training_sentence.text = training_sentence_text
                        training_sentence.is_false_positive = False
                        training_sentence.is_training_data = False
                        training_sentence.save()

                rule.save()

                self.stdout.write(self.style.SUCCESS(message))

    def add_diversity_dimension(
        self, rule: Rule, name: str, order: int, is_basic: bool = False
    ):
        subcategory_name = (
            name if not name.startswith("advanced_") else name.removeprefix("advanced_")
        )

        if name.endswith("_base"):
            subcategory_name = subcategory_name.removesuffix("_base")
            rule.type = RuleTypeEnum.SUFFIX

        subcategory_name = (
            subcategory_name if is_basic else subcategory_name + "_advanced"
        )

        try:
            diversity_dimensions_driver = DiversityDimension.objects.get(
                name=subcategory_name
            )

            rule_diversity_dimensions_driver = RuleDiversityDimension()
            rule_diversity_dimensions_driver.rule = rule
            rule_diversity_dimensions_driver.order = order
            rule_diversity_dimensions_driver.diversity_dimension = (
                diversity_dimensions_driver
            )
            rule_diversity_dimensions_driver.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Added diversity dimension '{subcategory_name}' from '{name}'."
                )
            )

        except DiversityDimension.DoesNotExist:
            rule.tags.add(name)
            self.stdout.write(self.style.SUCCESS(f"Added tag '{name}'."))
