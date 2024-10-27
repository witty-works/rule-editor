from django.core.management.base import BaseCommand
from rules.models import (
    Rule,
    Alternative,
    TrainingSentence,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
    Lemmatization,
    fetch_json,
)
import csv
import requests
from django.db import IntegrityError
from pluralizefr import pluralize


class Command(BaseCommand):
    help = "Imports french profession rules"
    diversity_dimensions = {}

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)
        parser.add_argument("--language", type=str)
        parser.add_argument("--limit", type=int, default=False)

    def handle(self, *args, **options):
        data = DiversityDimension.objects.filter()
        for diversity_dimension in data:
            self.diversity_dimensions[diversity_dimension.name] = diversity_dimension

        language = options["language"]
        limit = options["limit"]

        source = Source.objects.get(id=17)

        rules = {}
        with open(options["file"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if limit is not False and len(rules) == limit:
                    break

                masculine_form = (
                    row["Masculin"]
                    .lower()
                    .replace(" (de)", "")
                    .replace(" radio/TV", "")
                )
                feminine_form = (
                    row["Féminin"]
                    .lower()
                    .replace(" (vieilli)", "")
                    .replace(" (de)", "")
                    .replace(" radio/TV", "")
                )

                if "(" in masculine_form or "(" in feminine_form:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Skipping lemma '{masculine_form}' / '{feminine_form}' due to parenthesis"
                        )
                    )
                    continue

                self.stdout.write(
                    self.style.WARNING(f"Processing lemma '{masculine_form}'")
                )

                if "/" in masculine_form:
                    masculine_forms = masculine_form.split("/")
                    masculine_form = (
                        masculine_forms[0]
                        + ", "
                        + masculine_forms[0].rsplit(" ", 1)[0]
                        + " "
                        + masculine_forms[1]
                    )

                if "/" in feminine_form:
                    feminine_forms = feminine_form.split("/")
                    feminine_form = (
                        feminine_forms[0]
                        + ", "
                        + feminine_forms[0].rsplit(" ", 1)[0]
                        + " "
                        + feminine_forms[1]
                    )

                masculine_forms = masculine_form.split(",")
                feminine_forms = feminine_form.split(",")

                for i in range(len(feminine_forms)):
                    rule_diversity_dimensions = [
                        "titles",
                        "gender_identity_advanced",
                    ]

                    word_types = "n" if masculine_form.count(" ") == 0 else None

                    alternatives = {}

                    if i > 0:
                        previous_masculine_form = masculine_form
                        previous_feminine_form = feminine_form

                    feminine_form = feminine_forms[i].strip()

                    try:
                        masculine_form = masculine_forms[i].strip()
                        if masculine_form == feminine_form:
                            rule_diversity_dimensions.append("anglicism")
                            alternatives[
                                "un "
                                + previous_masculine_form
                                + "~une "
                                + previous_feminine_form
                            ] = False
                    except IndexError:
                        masculine_form = masculine_forms[0].strip()

                    masculine_lemma = masculine_form
                    feminine_lemma = feminine_form

                    sentences = [
                        "Il est un " + masculine_form,
                        "Elle est une " + feminine_form,
                    ]

                    if masculine_form == feminine_form:
                        masculine_lemma = "un " + masculine_lemma
                        feminine_lemma = "une " + feminine_lemma
                        if word_types is not None:
                            word_types = "|" + word_types

                    alternatives[masculine_lemma + "~" + feminine_lemma] = (
                        "anglicism" in rule_diversity_dimensions
                    )

                    rule = self.add_rule(
                        masculine_lemma, masculine_form, word_types, language, source
                    )
                    if rule is not None:
                        if feminine_form.count(" ") == 0:
                            self.check_lemmatization(
                                language, masculine_form, feminine_form
                            )
                            plural = pluralize(feminine_form)
                            was_added = self.check_lemmatization(
                                language, masculine_form, plural, True
                            )
                            if was_added:
                                sentences.append("Elles sont des " + plural)

                            plural = pluralize(masculine_form)
                            was_added = self.check_lemmatization(
                                language, masculine_form, plural, True
                            )
                            if was_added:
                                sentences.append("Ils sont des " + plural)

                        self.add_diversity_dimensions(rule, rule_diversity_dimensions)
                        self.add_alternatives(rule, alternatives, source)
                        self.add_sentences(rule, sentences)

                    if "anglicism" in rule_diversity_dimensions:
                        rule = self.add_rule(
                            masculine_form, masculine_form, "n", language, source
                        )
                        if rule is not None:
                            self.add_diversity_dimensions(rule, ["anglicism"])
                            self.add_alternatives(
                                rule, {next(iter(alternatives)): False}, source
                            )
                            self.add_sentences(rule, ["Il est un " + masculine_form])

    def add_rule(
        self, lemma: str, text_id: str, word_types: str, language: str, source: Source
    ):
        rules = Rule.objects.filter(lemma=lemma, language=language)
        if len(rules):
            self.stdout.write(
                self.style.ERROR(
                    f"Skipping lemma '{lemma}' as the rule already exists as '{rules[0]}' ({rules[0].id})"
                )
            )

            return

        rule = Rule()
        rule.lemma = lemma
        rule.text_id = text_id
        rule.word_types = word_types
        rule.language = language
        rule.is_marked_for_review = True
        rule.source = source
        rule.is_active = True
        rule.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created rule '{rule.lemma}' / '{rule.word_types}'"
            )
        )

        return rule

    def add_diversity_dimensions(
        self, rule: Rule, rule_diversity_dimensions: list[DiversityDimension]
    ):
        order = 0
        for diversity_dimension in rule_diversity_dimensions:
            rule_diversity_dimension = RuleDiversityDimension()
            rule_diversity_dimension.rule = rule
            rule_diversity_dimension.order = order
            rule_diversity_dimension.diversity_dimension = self.diversity_dimensions[
                diversity_dimension
            ]
            rule_diversity_dimension.save()
            order += 1

    def add_alternatives(
        self, rule: Rule, alternatives: dict[str, bool], source: Source
    ):
        order = 0
        for lemma in alternatives:
            alternative = Alternative()
            alternative.rule = rule
            alternative.language = rule.language
            alternative.lemma = lemma
            alternative.is_gendered_noun = True
            alternative.source = source
            alternative.order = order
            alternative.label = None if alternatives[lemma] else "⚠️ Anglicism"
            alternative.save()
            order += 1

    def add_sentences(self, rule: Rule, sentences: list[str]):
        for sentence in sentences:
            training_sentence = TrainingSentence()
            training_sentence.rule = rule
            training_sentence.text = sentence
            training_sentence.is_false_positive = False
            training_sentence.is_training_data = False
            training_sentence.save()

    def check_lemmatization(self, language, lemma, variation, is_plural=False):
        language = requests.utils.quote(language)
        feminine_form_query = requests.utils.quote(variation)
        path = f"/lemmatize?lang={language}&text={feminine_form_query}"
        lemmatized = fetch_json(path)
        if lemmatized != lemma:
            try:
                lemmatization = Lemmatization()
                lemmatization.language = language
                lemmatization.text = variation
                lemmatization.lemma = lemma
                lemmatization.is_plural = is_plural
                lemmatization.save()
            except IntegrityError as e:
                return False

        return True
