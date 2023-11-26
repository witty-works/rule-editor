from django.core.management.base import BaseCommand
from rules.models import (
    GermanVerb,
    GermanNoun,
    GenderTypeEnum,
    EnglishVerb,
    EnglishAdjective,
    EnglishNoun,
)
from german_nouns.lookup import Nouns
from inflex import Noun, Verb, Adjective
import csv


class Command(BaseCommand):
    help = "Imports Declensions"

    def add_arguments(self, parser):
        parser.add_argument("--germanverbs", type=str)
        parser.add_argument("--germannouns", type=str)

    def handle(self, *args, **options):
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

        if options["germannouns"]:
            with open(options["germannouns"]) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    text = row["lemma"]

                    try:
                        model = GermanNoun.objects.get(base_form=text)
                    except GermanNoun.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German noun '{text}' does not exist, skipping"
                            )
                        )
                        continue

                    if model.sg_nom_acc is not None:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German noun '{text}' already has 'sg_nom_acc' filled, skipping"
                            )
                        )
                        continue

                    model.gender_1 = row["Gender 1"]
                    model.gender_2 = row["Gender 2"] if row["Gender 2"] != "" else None
                    model.singular_only = True if row["Singular only"] != "" else False
                    model.plural_only = True if row["Plural only"] != "" else False
                    model.sg_nom_acc = row["sg-nom-acc"]
                    model.sg_dat = row["sg-dat"]
                    model.sg_gen = row["sg-gen"]
                    model.pl_nom_acc = row["pl-nom-acc"]
                    model.pl_gen = row["pl-gen"]
                    model.pl_dat = row["pl-dat"]
                    model.save()

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully updated German verb '{model.base_form}'"
                        )
                    )

        nouns = Nouns()
        genus_map = {
            "": None,
            "n": GenderTypeEnum.NEUTER,
            "f": GenderTypeEnum.FEMININE,
            "m": GenderTypeEnum.MASCULINE,
        }
        models = GermanNoun.objects.filter(gender_1=None)
        for model in models:
            result = nouns[model.base_form]
            if len(result) == 0 or len(result[0]["flexion"]) == 0:
                if "-" in model.base_form:
                    words = model.base_form.split("-")
                    word = words[-1]
                    words = "-".join(words[0:-1]) + "-"
                    lower = False
                else:
                    words = nouns.parse_compound(model.base_form)
                    if len(words) < 2:
                        self.stdout.write(
                            self.style.ERROR(
                                f"German noun could not split '{model.base_form}'"
                            )
                        )
                        continue

                    word = words[-1]
                    words = "".join(words[0:-1])
                    lower = True

                result = nouns[word]
                if len(result) == 0:
                    self.stdout.write(
                        self.style.ERROR(
                            f"German noun '{model.base_form}' could determine flexion for {word}"
                        )
                    )
                    continue

                for i in range(len(result)):
                    lemma = result[i]["lemma"].lower() if lower else result[i]["lemma"]
                    result[i]["lemma"] = words + lemma
                    for flexion in result[i]["flexion"]:
                        flexion_expanded = (
                            result[i]["flexion"][flexion].lower()
                            if lower
                            else result[i]["flexion"][flexion]
                        )

                        result[i]["flexion"][flexion] = words + flexion_expanded

            result = result[0]
            if "genus" not in result and "genus 1" not in result:
                self.stdout.write(
                    self.style.ERROR(
                        f"German noun '{model.base_form}' genus could not be determined"
                    )
                )
            else:
                model.gender_1 = (
                    genus_map[result["genus"]]
                    if "genus" in result
                    else genus_map[result["genus 1"]]
                )

            model.gender_2 = (
                genus_map[result["genus 2"]] if "genus 2" in result else None
            )
            singular = None
            singular_map = {
                "nominativ singular": "sg_nom_acc",
                "dativ singular": "sg_dat",
                "genitiv singular": "sg_gen",
            }

            plural = None
            plural_map = {
                "nominativ plural": "pl_nom_acc",
                "dativ plural": "pl_dat",
                "genitiv plural": "pl_gen",
            }

            for flexion in result["flexion"]:
                key = flexion.removesuffix(" 1")
                key = flexion.removesuffix(" stark")
                if key in singular_map:
                    setattr(model, singular_map[key], result["flexion"][flexion])
                    singular = True
                elif key in plural_map:
                    setattr(model, plural_map[key], result["flexion"][flexion])
                    plural = True

            model.singular_only = bool(singular and plural is None)
            model.plural_only = bool(plural and singular is None)
            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated German noun '{model.base_form}'"
                )
            )

        return

        models = EnglishVerb.objects.filter(past_tense=None)
        for model in models:
            inflex = Verb(model.base_form)
            model.past_tense = inflex.past()
            model.past_participle = inflex.past_part()
            model.present_participle = inflex.pres_part()
            model.third_person_singular = inflex.singular()
            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated English verb '{model.base_form}'"
                )
            )

        absolute = [
            "unique",
            "dead",
            "perfect",
            "alive",
            "universal",
            "complete",
            "unanimous",
            "final",
            "supreme",
            "unlimited",
            "absolute",
            "infinite",
            "total",
            "unmatched",
            "impossible",
            "immortal",
            "full",
            "irrevocable",
            "transcendent",
            "unknown",
            "unconditional",
            "ultimate",
            "empty",
            "unchanged",
            "married",
            "unquestionable",
            "transparent",
            "unrivaled",
            "single",
            "unbeatable",
            "invalid",
            "unbroken",
            "undeniable",
            "equal",
            "pregnant",
            "unsurpassed",
            "unequaled",
            "exhaustive",
            "superlative",
            "unrivaled",
            "essential",
            "eternal",
            "unbeatable",
            "permanent",
            "immutable",
            "indestructible",
            "unalterable",
            "immeasurable",
            "incomparable",
            "dummy",
        ]

        models = EnglishAdjective.objects.filter(comparative=None)
        for model in models:
            inflex = Adjective(model.base_form)
            if model.base_form.isupper():
                model.comparative = model.base_form
                model.superlative = model.base_form
            else:
                model.comparative = inflex.comparative()
                model.superlative = inflex.superlative()
            model.is_absolute = model.base_form in absolute
            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated English adjective '{model.base_form}'"
                )
            )

        models = EnglishNoun.objects.filter(plural=None)
        for model in models:
            inflex = Noun(model.base_form)
            model.plural = inflex.plural()
            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated English noun '{model.base_form}'"
                )
            )
