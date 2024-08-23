from django.core.management.base import BaseCommand
from rules.models import Alternative
import re

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix the lemma for point median alternatives"

    def add_arguments(self, parser):
        parser.add_argument("--issue", type=str, required=True)
        parser.add_argument("--lang", type=str, default=None)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--dry-run", type=bool, default=False)

    def handle(self, *args, **options):
        limit = options["limit"]
        lang = options["lang"]
        issue = options["issue"]
        dry_run = options["dry_run"]

        alternative = None
        count = 0

        try:
            alternatives = Alternative.objects

            if lang is not None:
                alternatives = alternatives.filter(language=lang)

            match issue:
                case "pointmedian":
                    alternatives = alternatives.extra(
                        where=["lemma LIKE %s OR lemma LIKE %s"],
                        params=["% %·%", "%·% %"],
                    )
                case "placeholder":
                    alternatives = alternatives.filter(lemma__contains="[")
                case _:
                    logger.error(f"Issue missing or not supported: {issue}")
                    return

            if limit is not None and limit > 0:
                alternatives = alternatives[0:limit]

            self.stdout.write(
                self.style.WARNING(f"Found {len(alternatives)} alternative")
            )

            for alternative in alternatives:
                original_lemma = alternative.lemma

                match issue:
                    case "pointmedian":
                        fix_pointmedian(alternative)
                    case "placeholder":
                        fix_placeholder(alternative)

                if dry_run == False:
                    alternative.save()
                count += 1

                self.stdout.write(
                    self.style.WARNING(
                        f"Updated alternative '{original_lemma}' to '{alternative.lemma}' - '{alternative.label}'"
                    )
                )
        except Exception as e:
            if alternative is not None:
                logger.error(f"Failed processing alternative '{alternative}': {e}")
            else:
                logger.error(f"Failed : {e}")

        self.stdout.write(self.style.WARNING(f"Updated {count} alternatives"))


def fix_pointmedian(alternative):
    male_form = ""
    female_form = ""

    words = alternative.lemma.split()
    for word in words:
        if male_form != "":
            male_form += " "
            female_form += " "

        if "·" in word:
            gender_form = word.split("·")

            male_form += gender_form[0]
            female_form += gender_form[1]
        else:
            male_form += word
            female_form += word

    alternative.lemma = male_form + "~" + female_form


def fix_placeholder(alternative: Alternative):
    if alternative.label is None or alternative.label == "":
        placeholders = re.findall("\[([^]]*)\]", alternative.lemma)
        placeholders = list(dict.fromkeys(placeholders))

        match alternative.language:
            case "en":
                alternative.label = f"specify '{placeholders[0]}'"
                conjunction = "and"
            case "fr":
                alternative.label = f"spécifier '{placeholders[0]}'"
                conjunction = "et"
            case "de":
                alternative.label = f"'{placeholders[0]}'"
                conjunction = "und"

        if len(placeholders) > 1:
            if len(placeholders) > 2:
                alternative.label += ", "
                alternative.label += ", ".join(
                    list(
                        map(lambda placeholder: f"'{placeholder}'", placeholders[1:-1])
                    )
                )

            alternative.label += f" {conjunction} '{placeholders[-1]}'"

        match alternative.language:
            case "de":
                alternative.label += " nennen"

    alternative.lemma = alternative.lemma.replace("[", "((").replace("]", "))")
