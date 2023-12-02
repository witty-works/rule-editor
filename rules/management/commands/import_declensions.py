from django.core.management.base import BaseCommand
from rules.models import (
    GermanVerb,
    GermanAdjective,
    GermanNoun,
    GenderTypeEnum,
    EnglishVerb,
    EnglishAdjective,
    EnglishNoun,
    Rule,
    PluralizationEnum,
    LanguageEnum,
)
from german_nouns.lookup import Nouns
from inflex import Noun, Verb, Adjective
import csv
import requests
from bs4 import BeautifulSoup


class Command(BaseCommand):
    help = "Imports Declensions"

    def add_arguments(self, parser):
        parser.add_argument("--language", type=LanguageEnum)
        parser.add_argument("--verbs", type=bool)
        parser.add_argument("--adjectives", type=bool)
        parser.add_argument("--nouns", type=bool)
        parser.add_argument("--germanverbs", type=str)
        parser.add_argument("--germannouns", type=str)

    def get_form(self, base_form, female_form=True):
        try:
            url = "https://de.wiktionary.org/wiki/" + base_form
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")

            title = (
                "Weibliche Varianten des Wortes"
                if female_form
                else "Männliche Wortformen Varianten des Wortes"
            )
            elements = soup.find_all("p", {"title": title})
            if len(elements):
                try:
                    return (
                        elements[0]
                        .find_next("dl")
                        .find("dd")
                        .find("a", attrs={"title": True})["title"]
                    ).removesuffix(" (Seite nicht vorhanden)")
                except AttributeError:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Fetching female unable to find child tag '{base_form}'"
                        )
                    )
                    pass
                except KeyError:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Fetching female could not find title '{base_form}'"
                        )
                    )
                    pass
                except Exception:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Fetching female failed to parse '{base_form}'"
                        )
                    )
        except requests.exceptions.ConnectionError:
            self.stdout.write(
                self.style.NOTICE(f"Fetching female failed to download '{base_form}'")
            )

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
        adjective_map = [
            "comparative",
            "superlative",
        ]

        models = GermanAdjective.objects.filter(comparative=None)
        for model in models:
            try:
                url = "https://de.wiktionary.org/wiki/" + model.base_form
                response = requests.get(url)
                soup = BeautifulSoup(response.text, "html.parser")
                elements = soup.find_all("span", {"id": "Adjektiv"})
                if len(elements) == 0:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Unable to fetch German adjective data '{model.base_form}'"
                        )
                    )
                    continue
                else:
                    try:
                        rows = elements[0].parent.find_next_sibling("table")
                        if rows is None:
                            model.is_absolute = True
                        else:
                            for row in rows.find("tbody").find_all("tr"):
                                columns = row.find_all("td")
                                if (
                                    len(columns)
                                    and len(columns[0].contents)
                                    and columns[0].contents[0].strip()
                                    == model.base_form
                                ):
                                    model.is_absolute = False
                                    for i in range(len(columns[1:])):
                                        element = columns[i + 1].find("a")
                                        if element is None:
                                            model.is_absolute = True
                                        else:
                                            setattr(
                                                model,
                                                adjective_map[i],
                                                columns[i + 1].find("a")["title"],
                                            )

                    except AttributeError:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Fetching German adjective unable to find tags '{model.base_form}'"
                            )
                        )
                        pass
                    except KeyError:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"Fetching German adjective could not find title '{model.base_form}'"
                            )
                        )
                        pass
                    except Exception as e:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"Fetching German adjective failed to parse '{model.base_form}'"
                            )
                        )
            except requests.exceptions.ConnectionError:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Fetching German adjective failed to download '{model.base_form}'"
                    )
                )

            if model.is_absolute:
                model.comparative = model.base_form
                model.superlative = model.base_form

            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated German adjective '{model.base_form}'"
                )
            )

    def german_nouns(self, options):
        nouns = Nouns()
        genus_map = {
            "": None,
            "n": GenderTypeEnum.NEUTER,
            "f": GenderTypeEnum.FEMININE,
            "m": GenderTypeEnum.MASCULINE,
        }
        models = GermanNoun.objects.filter(gender_1=None)
        for model in models:
            if not model.base_form[0].isupper():
                self.stdout.write(
                    self.style.ERROR(
                        f"German noun not capitalized, skipping '{model.base_form}'"
                    )
                )
                continue

            result = nouns[model.base_form]
            if len(result) == 0 or len(result[0]["flexion"]) == 0:
                if "-" in model.base_form:
                    words = model.base_form.split("-")
                    word = words[-1]
                    words = "-".join(words[0:-1]) + "-"
                    lower = False
                else:
                    words = nouns.parse_compound(model.base_form)
                    if len(words) < 1 or not model.base_form.endswith(words[-1]):
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
                            f"German noun '{model.base_form}' could not determine flexion for {word}"
                        )
                    )
                    continue

                if len(words) == 0:
                    lower = False

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

            singular = False
            singular_map = {
                "nominativ singular": "sg_nom",
                "dativ singular": "sg_dat",
                "dativ singular*": "sg_dat_2",
                "genitiv singular": "sg_gen",
                "genitiv singular*": "sg_gen_2",
                "akkusativ singular": "sg_acc",
            }

            plural = False
            plural_map = {
                "nominativ plural": "pl_nom",
                "dativ plural": "pl_dat",
                "dativ plural*": "pl_gen_2",
                "dativ plural": "pl_dat",
                "genitiv plural*": "pl_gen_2",
                "akkusativ plural": "pl_acc",
            }

            for flexion in result["flexion"]:
                # TODO handle variations (dativ/genetiv) and stark/schwach/gemischt
                key = flexion.removesuffix(" 1")
                key = flexion.removesuffix(" stark")
                if key in singular_map:
                    setattr(model, singular_map[key], result["flexion"][flexion])
                    singular = True
                elif key in plural_map:
                    setattr(model, plural_map[key], result["flexion"][flexion])
                    plural = True

            if not singular and not plural:
                self.stdout.write(
                    self.style.ERROR(
                        f"Unable to find flexion data for German noun '{model.base_form}'"
                    )
                )
                continue

            model.singular_only = bool(singular and not plural)
            model.plural_only = bool(plural and not singular)

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

            if model.female_form is None:
                model.female_form = self.get_form(model.base_form)

            if model.female_form is None and model.male_form is None:
                model.male_form = self.get_form(model.base_form, False)

            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated German noun '{model.base_form}'"
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

    def english_adjectives(self):
        models = EnglishAdjective.objects.filter(comparative=None)
        for model in models:
            model.is_absolute = model.base_form[0].isupper()
            if model.is_absolute == False:
                try:
                    url = "https://en.wiktionary.org/wiki/" + model.base_form
                    response = requests.get(url)
                    soup = BeautifulSoup(response.text, "html.parser")
                    element = soup.find("span", {"id": "Adjective"})
                    if element is None:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"English adjective data missing '{model.base_form}'"
                            )
                        )

                        continue

                    element = element.find_next("p")

                    uncomparable = element.find(
                        "a", {"href": "/wiki/Appendix:Glossary#uncomparable"}
                    )
                    if uncomparable:
                        model.is_absolute = True
                    else:
                        not_generally = element.select_one(
                            'i:-soup-contains("not generally")'
                        )
                        if not_generally:
                            model.is_absolute = True
                        else:
                            element.find(
                                "a", {"href": "/wiki/Appendix:Glossary#comparative"}
                            )
                            comparative = element.find(
                                "a", {"href": "/wiki/Appendix:Glossary#comparative"}
                            )
                            model.is_absolute = not bool(comparative)
                except requests.exceptions.ConnectionError:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Fetching english adjective failed to download '{model.base_form}'"
                        )
                    )

            if model.is_absolute:
                model.comparative = model.base_form
                model.superlative = model.base_form
            else:
                inflex = Adjective(model.base_form)
                model.comparative = inflex.comparative()
                model.superlative = inflex.superlative()

            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated English adjective '{model.base_form}'"
                )
            )

    def english_nouns(self):
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

    def handle(self, *args, **options):
        if options["language"] == "de":
            self.german(options)

        elif options["language"] == "en":
            self.english(options)
