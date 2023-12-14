from django.core.management.base import BaseCommand
from rules.models import (
    GermanVerb,
    GermanAdjective,
    GermanNoun,
    EnglishVerb,
    EnglishAdjective,
    EnglishNoun,
    Rule,
    PluralizationEnum,
    LanguageEnum,
)
import csv


class Command(BaseCommand):
    help = "Imports Declensions"

    def add_arguments(self, parser):
        parser.add_argument("--language", type=LanguageEnum)
        parser.add_argument("--verbs", type=bool)
        parser.add_argument("--adjectives", type=bool)
        parser.add_argument("--nouns", type=bool)
        parser.add_argument("--germanverbs", type=str)
        parser.add_argument("--germannouns", type=str)

    def german(self, options):
        if options["verbs"]:
            self.german_verbs(options)

        if options["adjectives"]:
            self.german_adjectives()

        if options["nouns"]:
            self.german_nouns(options)

    def german_verbs(self, options):
        if options["germanverbs"]:
            with open(options["germanverbs"]) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    text = row["infinitiv"]

                    try:
                        model = GermanVerb.objects.get(base_form=text)
                    except GermanVerb.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German verb '{text}' does not exist, skipping"
                            )
                        )
                        continue

                    if model.past_participle is not None:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German verb '{text}' already has 'past_participle' filled, skipping"
                            )
                        )
                        continue

                    model.present_ich = row["present_ich"]
                    model.present_du = row["present_du"]
                    model.present_pronoun = row["present_pronoun"]
                    model.past_tense_ich = row["past_tense_ich"]
                    model.past_participle = row["past_participle"]
                    model.conjunctive_ich = row["conjunctive_ich"]
                    model.imperativ_singular = row["imperativ_singular"]
                    model.imperativ_plural = row["imperativ_plural"]
                    model.helping_verb = row["helping_verb"]
                    model.infinitiv_zu = row["infinitiv_zu"]
                    model.save()

                    self.stdout.write(
                        self.style.ERROR(
                            f"Successfully updated German verb '{model.base_form}'"
                        )
                    )

    def german_adjectives(self):
        models = GermanAdjective.objects.filter(comparative=None)
        for model in models:
            failed, message = model.fill_declensions()

            message = model.base_form + ": " + message
            message = (
                self.style.ERROR(message) if failed else self.style.SUCCESS(message)
            )
            self.stdout.write(message)

    def german_nouns(self, options):
        models = GermanNoun.objects.filter(gender_1=None)
        for model in models:
            if not model.base_form[0].isupper():
                self.stdout.write(
                    self.style.ERROR(
                        f"German noun not capitalized, skipping '{model.base_form}'"
                    )
                )
                continue

            failed, message = model.fill_declensions()

            message = model.base_form + ": " + message
            message = (
                self.style.ERROR(message) if failed else self.style.SUCCESS(message)
            )
            self.stdout.write(message)

        if options["germannouns"]:
            with open(options["germannouns"]) as f:
                reader = csv.DictReader(f)

                for row in reader:
                    text = row["lemma"]

                    try:
                        model = GermanNoun.objects.get(base_form=text)
                    except GermanNoun.DoesNotExist:
                        model = GermanNoun()
                        model.base_form = text

                    new_row = {}
                    new_row["gender_1"] = row["Gender 1"]
                    new_row["gender_2"] = (
                        row["Gender 2"] if row["Gender 2"] != "" else None
                    )

                    new_row["sg_nom"] = row["sg-nom"]
                    new_row["sg_dat"] = row["sg-dat"]
                    new_row["sg_gen"] = row["sg-gen"]
                    new_row["sg_acc"] = row["sg-acc"]
                    new_row["pl_nom"] = row["pl-nom"]
                    new_row["pl_gen"] = row["pl-gen"]
                    new_row["pl_dat"] = row["pl-dat"]
                    new_row["pl_acc"] = row["pl-acc"]

                    new_row["singular_only"] = bool(
                        not new_row["pl_nom"]
                        and not new_row["pl_dat"]
                        and not new_row["pl_gen"]
                        and not new_row["pl_acc"]
                    )
                    new_row["plural_only"] = bool(
                        not new_row["sg_nom"]
                        and not new_row["sg_dat"]
                        and not new_row["sg_gen"]
                        and not new_row["sg_acc"]
                    )

                    if row["Singular only"] == "TRUE" or row["Plural only"] == "TRUE":
                        try:
                            rule = Rule.objects.filter(
                                lemma=model.base_form, word_types="n"
                            ).get()

                            changed = False
                            if (
                                row["Singular only"] == "TRUE"
                                and rule.pluralization
                                != PluralizationEnum.SINGULAR_ONLY
                            ):
                                rule.pluralization = PluralizationEnum.SINGULAR_ONLY
                                changed = True
                            if (
                                row["Plural only"] == "TRUE"
                                and rule.pluralization != PluralizationEnum.PLURAL_ONLY
                            ):
                                rule.pluralization = PluralizationEnum.PLURAL_ONLY
                                changed = True

                            if changed:
                                rule.save()

                                self.style.SUCCESS(
                                    f"German noun rule for '{model.base_form}' pluralization updated to {rule.pluralization}."
                                )
                        except Rule.DoesNotExist:
                            self.style.ERROR(
                                f"German noun rule for '{model.base_form}' not found for pluralization update."
                            )

                    data_mis_match = ""
                    has_changes = False
                    for field in new_row:
                        current_value = getattr(model, field)
                        if current_value != new_row[field]:
                            has_changes = True

                        if (
                            current_value is not None
                            and current_value != ""
                            and current_value != new_row[field]
                        ):
                            new_value = (
                                "NONE" if new_row[field] is None else new_row[field]
                            )
                            data_mis_match += (
                                f"'{field}' is '{current_value}' -> '{new_value}', "
                            )

                    if model.sg_nom and data_mis_match != "":
                        self.stdout.write(
                            self.style.ERROR(
                                f"German noun '{model.base_form}' has a data mismatch on fields {data_mis_match} skipping"
                            )
                        )
                        continue

                    if has_changes == False:
                        continue

                    model.gender_1 = new_row["gender_1"]
                    model.gender_2 = new_row["gender_2"]
                    model.singular_only = new_row["singular_only"]
                    model.plural_only = new_row["plural_only"]
                    model.sg_nom = new_row["sg_nom"]
                    model.sg_dat = new_row["sg_dat"]
                    model.sg_gen = new_row["sg_gen"]
                    model.sg_acc = new_row["sg_acc"]
                    model.pl_nom = new_row["pl_nom"]
                    model.pl_gen = new_row["pl_gen"]
                    model.pl_dat = new_row["pl_dat"]
                    model.pl_acc = new_row["pl_acc"]
                    model.save()

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully updated German noun '{model.base_form}'"
                        )
                    )

    def english(self, options):
        if options["verbs"]:
            self.english_verbs()

        if options["adjectives"]:
            self.english_adjectives()

        if options["nouns"]:
            self.english_nouns()

    def english_verbs(self):
        models = EnglishVerb.objects.filter(past_tense=None)
        for model in models:
            failed, message = model.fill_declensions()

            message = model.base_form + ": " + message
            message = (
                self.style.ERROR(message) if failed else self.style.SUCCESS(message)
            )
            self.stdout.write(message)

    def english_adjectives(self):
        models = EnglishAdjective.objects.filter(comparative=None)
        for model in models:
            failed, message = model.fill_declensions()

            message = model.base_form + ": " + message
            message = (
                self.style.ERROR(message) if failed else self.style.SUCCESS(message)
            )
            self.stdout.write(message)

    def english_nouns(self):
        models = EnglishNoun.objects.filter(plural=None)
        for model in models:
            failed, message = model.fill_declensions()

            message = model.base_form + ": " + message
            message = (
                self.style.ERROR(message) if failed else self.style.SUCCESS(message)
            )
            self.stdout.write(message)

    def handle(self, *args, **options):
        if options["language"] == "de":
            self.german(options)

        elif options["language"] == "en":
            self.english(options)
