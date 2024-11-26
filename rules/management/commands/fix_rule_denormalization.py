from django.core.management.base import BaseCommand
from rules.models import Rule

import json
import ast


class Command(BaseCommand):
    help = "Update rule_translation_source"

    def handle(self, *args, **options):
        rules = Rule.objects.filter()

        count = 0
        for rule in rules:
            count += 1
            if count % 100 == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Processed {count} rules (current rule {rule})."
                    )
                )

            try:
                rule.save()
            except:
                self.stdout.write(self.style.ERROR(f"Failure processing rule {rule}."))

        self.stdout.write(
            self.style.SUCCESS(f"Processed {count} rules (current rule {rule}).")
        )
