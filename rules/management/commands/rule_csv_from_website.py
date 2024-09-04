from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup

import csv
import re


class Command(BaseCommand):
    help = "Generate CSV with Rules from Website"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True)
        parser.add_argument("--output-file", type=str, required=True)

    def remove_whitespace(self, element):
        return re.sub(r"\s+", " ", element.get_text().replace("\n", " "))

    def removeprefix(self, text, list: list[str]):
        for item in list:
            item += " "
            text = text.removeprefix(item)
            text = text.removeprefix(item.capitalize())

        return text

    def handle(self, *args, **options):
        file = options["file"]
        output_file = options["output_file"]

        try:
            f = open(file, "r")
            contents = f.read()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to read file '{file}': {e}"))
            return

        soup = BeautifulSoup(contents, "html.parser")

        with open(output_file, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            fields = [
                "lemma",
                "rule lemma",
                "rule text",
                "alternative_text",
                "alternatives ..",
            ]
            writer.writerow(fields)

            conjunctions = ["et", "ou"]
            articles = ["les", "un", "une", "le", "l’", "la"]

            elements = soup.find_all("details", {"class": "main-accordion"})
            for element in elements:
                if element["id"] is None or element["id"].count("-") != 1:
                    self.stdout.write(
                        self.style.ERROR(
                            f"details ID is missing nor malformatted {element}"
                        )
                    )
                    continue

                _, id = element["id"].split("-")

                lemma = element.find("h3")

                if lemma is None:
                    self.stdout.write(
                        self.style.ERROR(f"h3 with lemma data not found {element}")
                    )
                    continue

                lemma = self.remove_whitespace(lemma)

                if "participe passé" in lemma:
                    self.stdout.write(
                        self.style.ERROR(f"ignore participes passés for {lemma}")
                    )
                    continue

                table = element.find(
                    id=f"paragraph-inclusionnaire_exemples_solution{id}"
                )
                if table is None:
                    self.stdout.write(
                        self.style.ERROR(f"table id '{id}' not found for {lemma}")
                    )
                    continue

                fields = [lemma]
                writer.writerow(fields)

                trs = table.find_all("tr")
                for tr in trs:
                    ths = tr.find_all("th")
                    if len(ths):
                        continue

                    tds = tr.find_all("td")
                    if len(tds) != 2:
                        self.stdout.write(
                            self.style.ERROR(f"Row data malformed {tr} for {lemma}")
                        )
                        continue

                    rule = tds[0].find("div")

                    rule_lemma = rule.find("strong")
                    if rule_lemma is None:
                        self.stdout.write(
                            self.style.ERROR(
                                f"No highlighted lemma found in {tds[0]} for {lemma}"
                            )
                        )
                        continue

                    rule_lemma = self.remove_whitespace(rule_lemma)
                    rule_lemma = self.removeprefix(rule_lemma, ["le", "l’", "un"])

                    alternatives = tds[1].find_all("ul")
                    alternatives_text = ""
                    for alternative in alternatives:
                        alternatives_text += (
                            f"* {self.remove_whitespace(alternative)}\n"
                        )

                    fields = [
                        "",
                        rule_lemma,
                        self.remove_whitespace(rule),
                        alternatives_text,
                    ]

                    for alternative in tds[1].find_all("strong"):
                        alternative = self.remove_whitespace(alternative)

                        words = alternative.split()
                        alternative = words[0]
                        word_index = 1
                        while word_index < len(words):
                            if (
                                word_index + 1 < len(words)
                                and words[word_index] in conjunctions
                                and words[word_index - 1][0:3].lower()
                                == words[word_index + 1][0:3].lower()
                            ):
                                words[word_index] = "~"
                                word_index += 1
                            else:
                                words[word_index] = f" {words[word_index]}"

                            word_index += 1

                        alternative = "".join(words)
                        alternative = self.removeprefix(alternative, articles)
                        alternative = alternative.replace("[", "((").replace("]", "))")
                        fields.append(alternative)

                    writer.writerow(fields)
