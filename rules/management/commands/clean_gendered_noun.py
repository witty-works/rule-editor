from django.core.management.base import BaseCommand
from rules.models import (
    Rule,
    Alternative,
    GermanNoun,
)


class Command(BaseCommand):
    help = "Cleans up alternatives to use is_gendered_noun"

    def handle(self, *args, **options):
        lemmas = [
            "Bäuerin~Bauer",
            "Ärztin~Arzt",
            "Anwältin~Anwalt",
            "Bundesrätin~Bundesrat",
            "Jüdin~Jude",
            "Köchin~Koch",
            "Nationalrätin~Nationalrat",
            "Polisseuse~Polisseur",
            "Zimmerfrau~Zimmermann",
            "Fachfrau~Fachmann",
            "Kauffrau~Kaufmann",
            "Bankkauffrau~Bankkaufmann",
        ]

        rules = Rule.objects.filter(language="de")
        for rule in rules:
            gendered_alternatives = []
            alternatives_to_remove = []
            collective_nouns = {}
            alternatives = Alternative.objects.filter(rule_id=rule.id, is_inspiration=0)
            for alternative in alternatives:
                if "~/~" in alternative.lemma or alternative.lemma in lemmas:
                    gendered_alternatives.append(alternative)

                elif "~ und ~" in alternative.lemma:
                    alternatives_to_remove.append(alternative)
                elif alternative.lemma.endswith("schaft") or alternative.lemma.endswith(
                    "ende"
                ):
                    collective_nouns[alternative.lemma] = alternative

            if len(gendered_alternatives) == 0:
                continue

            # self.stdout.write(self.style.SUCCESS(f"cleaning rule {rule.lemma}"))

            for alternative in alternatives_to_remove:
                # self.stdout.write(self.style.SUCCESS(f"deleting {alternative.lemma}"))
                alternative.delete()

            for gendered_alternative in gendered_alternatives:
                original_lemma = gendered_alternative.lemma
                separator = "~" if gendered_alternative.lemma in lemmas else "~/~"

                words = gendered_alternative.lemma.split(" ")
                lemma_nouns = []
                if len(words) > 1:
                    self.stdout.write(
                        self.style.ERROR(
                            f"{rule.lemma} cannot handle german noun defintion for {gendered_alternative.lemma}"
                        )
                    )

                lemma = ""
                for i in range(len(words)):
                    word = words[i]
                    if (
                        word[0].isupper()
                        and separator in word
                        and not word.startswith("~")
                    ):
                        noun = word.split(separator)
                        noun[0] = noun[0].replace("~", "")
                        noun = {"male_form": noun[1], "female_form": noun[0]}
                        lemma_nouns.append(noun)
                        lemma += "~" + noun["male_form"] + "~" + " "
                    else:
                        if "~/~" in word:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"{rule.lemma} alternative {gendered_alternative.lemma}, '{word}' contains '~/~'"
                                )
                            )

                        lemma += word + " "

                for lemma_noun in lemma_nouns:
                    for key in lemma_noun:
                        try:
                            noun = GermanNoun.objects.get(base_form=lemma_noun[key])
                        except GermanNoun.DoesNotExist:
                            noun = GermanNoun()
                            noun.base_form = lemma_noun[key]
                            if noun.comment is None:
                                noun.comment = ""
                            else:
                                noun.comment += "\n"

                            noun.comment += (
                                f"Added legacy rule {rule.lemma} for {original_lemma}"
                            )

                            _, message = noun.fill_declensions()
                            self.stdout.write(
                                self.style.WARNING(
                                    f"{rule.lemma} creating missing german noun defintion for {lemma_noun[key]} ({key}): "
                                    + message
                                    + " - "
                                    + ", ".join(collective_nouns.keys())
                                )
                            )

                            if key == "female_form":
                                noun.male_form = lemma_noun["male_form"]
                            else:
                                noun.female_form = lemma_noun["female_form"]

                        field = "collective_noun"
                        failure = True
                        if len(lemma_nouns) == 1:
                            failure = False
                            keys = list(collective_nouns.keys())
                            for collective_noun_key in keys:
                                collective_noun = collective_nouns[
                                    collective_noun_key
                                ].lemma
                                if collective_noun.startswith("~"):
                                    collective_noun = collective_noun[1:]

                                if " " in collective_noun or "_2_2" in field:
                                    failure = True
                                elif collective_noun.startswith(noun.base_form[0:4]):
                                    setattr(noun, field, collective_noun)
                                    field += "_2"
                                    collective_nouns[collective_noun_key].delete()
                                    del collective_nouns[collective_noun_key]

                        if failure:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"{rule.lemma} collective nouns issue {gendered_alternative.lemma}: "
                                    + ", ".join(collective_nouns.keys())
                                )
                            )

                        noun.save()

                gendered_alternative.lemma = lemma.strip()
                gendered_alternative.is_gendered_noun = True
                gendered_alternative.pluralization = "default"
                gendered_alternative.save()

                # self.stdout.write(
                #    self.style.SUCCESS(f"cleaned from {original_lemma} to {gendered_alternative.lemma}")
                # )
