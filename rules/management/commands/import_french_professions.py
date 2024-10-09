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

    def generate_plural(self, lemma, is_masculine=True):
        if lemma.startswith("grand-") and is_masculine:
            lemma = "grands-" + lemma[6:]

        if lemma.endswith("s") or lemma.endswith("x") or lemma.endswith("z"):
            return lemma

        if lemma.endswith("au") or lemma.endswith("eu") or lemma.endswith("ou"):
            return lemma + "x"

        if lemma.endswith("al"):
            return lemma[0:-2] + "aux"

        if lemma.endswith("ail"):
            return lemma[0:-3] + "aux"

        return lemma + "s"


# Code taken from https://github.com/sblondon/pluralizefr/blob/da2b525bfadde87b408d0a7f290c8892f1fc8726/pluralizefr/__init__.py License: BSD-3-Clause license

"""Pluralize word according French grammar rules

Special cases are based on:
http://fr.wiktionary.org/wiki/Annexe:Pluriels_irr%C3%A9guliers_en_fran%C3%A7ais
"""


def pluralize(word, is_masculine=True):
    if word.startswith("grand-") and is_masculine:
        word = "grands-" + word[6:]

    for GRAMMAR_RULE in (
        _ail_word,
        _al_word,
        _au_word,
        _eil_word,
        _eu_word,
        _ou_word,
        _s_word,
        _x_word,
        _z_word,
        _default,
    ):
        plural = GRAMMAR_RULE(word)
        if plural:
            return plural


def _ail_word(word):
    if word.endswith("ail"):
        if word == "ail":
            return "aulx"
        elif word in (
            "bail",
            "corail",
            "émail",
            "fermail",
            "soupirail",
            "travail",
            "vantail",
            "ventail",
            "vitrail",
        ):
            return word[:-3] + "aux"
        return word + "s"


def _al_word(word):
    if word.endswith("al"):
        if word in (
            "bal",
            "carnaval",
            "chacal",
            "festival",
            "récital",
            "régal",
            "bancal",
            "fatal",
            "fractal",
            "final",
            "morfal",
            "natal",
            "naval",
            "aéronaval",
            "anténatal",
            "néonatal",
            "périnatal",
            "postnatal",
            "prénatal",
            "tonal",
            "atonal",
            "bitonal",
            "polytonal",
            "corral",
            "deal",
            "goal",
            "autogoal",
            "revival",
            "serial",
            "spiritual",
            "trial",
            "caracal",
            "chacal",
            "gavial",
            "gayal",
            "narval",
            "quetzal",
            "rorqual",
            "serval",
            "metical",
            "rial",
            "riyal",
            "ryal",
            "cantal",
            "emmental",
            "emmenthal",
            "floréal",
            "germinal",
            "prairial",
        ):
            return word + "s"
        return word[:-2] + "aux"


def _au_word(word):
    if word.endswith("au"):
        if word in ("berimbau", "donau", "karbau", "landau", "pilau", "sarrau", "unau"):
            return word + "s"
        return word + "x"


def _eil_word(word):
    if word.endswith("eil"):
        return "vieux" if word == "vieil" else word + "s"


def _eu_word(word):
    if word.endswith("eu"):
        if word in ("bleu", "émeu", "enfeu", "pneu", "rebeu"):
            return word + "s"
        return word + "x"


def _ou_word(word):
    if word.endswith("ou"):
        if word in ("bijou", "caillou", "chou", "genou", "hibou", "joujou", "pou"):
            return word + "x"
        return word + "s"


def _s_word(word):
    if word[-1] == "s":
        return word


def _x_word(word):
    if word[-1] == "x":
        return word


def _z_word(word):
    if word[-1] == "z":
        return word


def _default(word):
    return word + "s"


def singularize(word):
    for GRAMMAR_RULE in (
        _eau_word_sing,
        _ail_word_sing,
        _eil_word_sing,
        _eu_word_sing,
        _ou_word_sing,
        _s_word_sing,
        _default_sing,
    ):
        singular = GRAMMAR_RULE(word)
        if singular:
            return singular


def _eau_word_sing(word):
    if word.endswith("eaux"):
        return word[:-1]


def _ail_word_sing(word):
    if word == "aulx":
        return "ail"
    if word.endswith("aux"):
        if word in (
            "baux",
            "coraux",
            "émaux",
            "fermaux",
            "soupiraux",
            "travaux",
            "vantaux",
            "ventaux",
            "vitraux",
        ):
            return word[:-3] + "ail"
        else:
            return word[:-3] + "al"


def _eil_word_sing(word):
    if word == "vieux":
        return "vieil"


def _eu_word_sing(word):
    if word.endswith("eus") or word.endswith("eux"):
        return word[:-1]


def _ou_word_sing(word):
    if word.endswith("oux"):
        if word in (
            "bijoux",
            "cailloux",
            "choux",
            "genoux",
            "hiboux",
            "joujoux",
            "poux",
        ):
            return word[:-1]
        else:
            return word


def _s_word_sing(word):
    if word.endswith("s"):
        if word in (
            "abcès",
            "accès",
            "abus",
            "albatros",
            "anchois",
            "anglais",
            "autobus",
            "brebis",
            "carquois",
            "cas",
            "chas",
            "colis",
            "concours",
            "corps",
            "cours",
            "cyprès",
            "décès",
            "devis",
            "discours",
            "dos",
            "embarras",
            "engrais",
            "entrelacs",
            "excès",
            "fois",
            "fonds",
            "gâchis",
            "gars",
            "glas",
            "guet-apens",
            "héros",
            "intrus",
            "jars",
            "jus",
            "kermès",
            "lacis",
            "legs",
            "lilas",
            "marais",
            "matelas",
            "mépris",
            "mets",
            "mois",
            "mors",
            "obus",
            "os",
            "palais",
            "paradis",
            "parcours",
            "pardessus",
            "pays",
            "plusieurs",
            "poids",
            "pois",
            "pouls",
            "printemps",
            "processus",
            "progrès",
            "puits",
            "pus",
            "rabais",
            "radis",
            "recors",
            "recours",
            "refus",
            "relais",
            "remords",
            "remous",
            "rhinocéros",
            "repas",
            "rubis",
            "sas",
            "secours",
            "souris",
            "succès",
            "talus",
            "tapis",
            "taudis",
            "temps",
            "tiers",
            "univers",
            "velours",
            "verglas",
            "vernis",
            "virus",
            "accordailles",
            "affres",
            "aguets",
            "alentours",
            "ambages",
            "annales",
            "appointements",
            "archives",
            "armoiries",
            "arrérages",
            "arrhes",
            "calendes",
            "cliques",
            "complies",
            "condoléances",
            "confins",
            "dépens",
            "ébats",
            "entrailles",
            "épousailles",
            "errements",
            "fiançailles",
            "frais",
            "funérailles",
            "gens",
            "honoraires",
            "matines",
            "mœurs",
            "obsèques",
            "pénates",
            "pierreries",
            "préparatifs",
            "relevailles",
            "rillettes",
            "sévices",
            "ténèbres",
            "thermes",
            "us",
            "vêpres",
            "victuailles",
        ):
            return word
        else:
            return word[:-1]


def _default_sing(word):
    return word
