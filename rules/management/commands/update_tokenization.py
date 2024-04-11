from django.core.management.base import BaseCommand
from rules.models import Rule
from computedfields.models import compute


class Command(BaseCommand):
    help = "Update tokenizations"

    def handle(self, *args, **options):
        rules = Rule.objects.all()

        for rule in rules:
            rule.clean()
            computed = compute(rule, "lemma_json")
            if computed != rule.lemma_json:
                self.stdout.write(
                    self.style.ERROR(
                        f"Lemma json mismatch for rule {rule}, lemma_json '{rule.lemma_json}' does not match computed '{computed}'"
                    )
                )

            for alternative in rule.alternatives.all():
                alternative.clean()
                computed = compute(alternative, "lemma_json")
                if computed != alternative.lemma_json:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Lemma json mismatch for alternative {alternative} for rule {rule}, lemma_json '{alternative.lemma_json}' does not match computed '{computed}'"
                        )
                    )
                    alternative.save()
