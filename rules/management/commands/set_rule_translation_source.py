from django.core.management.base import BaseCommand
from rules.models import Rule

import json
import ast


class Command(BaseCommand):
    help = "Update rule_translation_source"

    def handle(self, *args, **options):
        rules = Rule.objects.filter(
            rule_translation_source=None, is_auto_generated=True
        )
        for rule in rules:
            self.stdout.write(self.style.WARNING(f"Updating rule {rule}"))

            if rule.source_rule:
                rule.source_rule = (
                    rule.source_rule.replace('n"t', "n't")
                    .replace('it"s', "it's")
                    .replace('"derp,"', "'derp,'")
                    .replace('"derp"', "'derp'")
                    .replace('"donut-puncher"', "'donut-puncher'")
                    .replace('mother"s', "mother's")
                    .replace('He"s', "He's")
                    .replace('you"re', "you're")
                    .replace('"You mother trucker!"', "'You mother trucker!'")
                    .replace('"dot or feather?"', "'dot or feather?'")
                    .replace('"Dot or feather?"', "'Dot or feather?'")
                    .replace('city"s', "city's")
                    .replace('website"s', "website's")
                    .replace('"finocchio"', "'finocchio'")
                    .replace('"s ', "'s ")
                    .replace('"s)', "'s)")
                    .replace('I"m', "I'm")
                    .replace('"that\'s so gay."', "'that's so gay.'")
                    .replace('"Sincerely"', "'Sincerely'")
                    .replace('"Dear Sir"', "'Dear Sir'")
                    .replace('I"ve', "I've")
                    .replace('"paki"', "'paki'")
                    .replace('they"re', "they're")
                )
                source = ast.literal_eval(rule.source_rule)

                try:
                    source_rule = Rule.objects.filter(
                        lemma=source["rule_specification"]["lemma"],
                        word_types=source["rule_specification"]["word_type"],
                    )[:1].get()
                    if source_rule:
                        rule.rule_translation_source = source_rule
                        rule.source_rule = json.dumps(source, indent=2)
                        rule.save()

                        for evaluation in rule.evaluations.all():
                            evaluation.rule_source_rule = rule.source_rule
                            evaluation.save()

                        self.stdout.write(
                            self.style.SUCCESS(
                                "Updated source to: " + source_rule.lemma
                            )
                        )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(str(e)))
