from django.core.management.base import BaseCommand
from rules.admin import apply_rule
from rules.models import Rule, TrainingSentence
from django.core.mail import send_mail


class Command(BaseCommand):
    help = (
        "Checks that rules work as expected (training sentence response is not empty)"
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str)

    def handle(self, *args, **options):
        new_failing_rules = new_passing_rules = failing_rules = 0

        results = []

        rules = Rule.objects.all()
        for rule in rules:
            self.stdout.write(self.style.WARNING(f"Checking rule {rule}"))

            training_sentences = TrainingSentence.objects.filter(rule=rule)
            if len(training_sentences):
                failing = False

                for sentence in training_sentences:
                    if sentence.is_false_positive:  # dont expect this to work yet
                        continue

                    try:
                        response = apply_rule({"rule": rule.id, "text": sentence.text})
                    except:
                        continue

                    failing = False
                    result_prefix = "=" if rule.has_failing_training_sentence else ">"
                    if len(response) == 0:
                        if not sentence.is_false_positive:
                            results.append(
                                f"{result_prefix} Response is empty for rule {rule} and sentence {sentence}"
                            )
                            self.stdout.write(self.style.ERROR(results[-1]))
                            failing = True
                    elif sentence.is_false_positive:
                        results.append(
                            f"{result_prefix} Response is not for rule {rule} and sentence {sentence} for a false positive"
                        )
                        self.stdout.write(self.style.ERROR(results[-1]))
                        failing = True

                if failing:
                    failing_rules += 1
                    new_failing_rule = self.mark_as_failing(rule)
                    new_failing_rules += new_failing_rule
                else:
                    new_passing_rule = self.mark_as_passing(rule)
                    new_passing_rules += new_passing_rule

                    if new_passing_rule:
                        results.append(
                            f"> Newly passing rule {rule} and sentence {sentence}"
                        )
                        self.stdout.write(self.style.SUCCESS(results[-1]))

            else:
                self.stdout.write(
                    self.style.ERROR(f"No training sentences for rule {rule}")
                )

        if failing_rules:
            results.append(
                f"Checked {len(rules)} rules. There are {failing_rules} failing rules with {new_failing_rules} newly failing rules and {new_passing_rules} newly passing rules"
            )
            self.stdout.write(self.style.ERROR(results[-1]))

        if options["email"]:
            send_mail(
                "Rule Editor: Nightly checks",
                "\n".join(results),
                "engineering@witty.works",
                [options["email"]],
                fail_silently=False,
            )

    def mark_as_failing(self, rule: Rule):
        if rule.has_failing_training_sentence:
            return 0

        rule.has_failing_training_sentence = True
        rule.save()
        return 1

    def mark_as_passing(self, rule: Rule):
        if rule.has_failing_training_sentence == False:
            return 0

        rule.has_failing_training_sentence = False
        rule.save()
        return 1
