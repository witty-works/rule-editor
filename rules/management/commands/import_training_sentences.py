import json

from django.core.management import call_command
from django.core.management.base import BaseCommand

from rules.evaluation import analyze_text, build_rule_payload, evaluate_sentence
from rules.models import Rule, TrainingSentence


class Command(BaseCommand):
    help = (
        "Import chat-generated training sentences from JSONL "
        '({"rule_id", "sentences": [...], "negative_sentences": [...]}). '
        "Each positive sentence must actually trigger the rule (checked "
        "against the live NLP API - the authoritative test that a matchable "
        "form is present in the declared word type's position); negative "
        "sentences must NOT trigger it. Rules with false-positive lists "
        "require at least one near-miss negative containing the rule word. "
        "Valid sentences are stored and the touched rules are re-evaluated "
        "immediately so the new sentences get versioned pass/fail state."
    )

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True, nargs="+")
        parser.add_argument(
            "--apply", action="store_true", help="Write sentences (dry-run otherwise)"
        )
        parser.add_argument(
            "--lenient",
            action="store_true",
            help="Import valid sentences even when others in the same rule fail "
            "validation (default: a rule is all-or-nothing)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        if not apply:
            self.stdout.write(self.style.WARNING("Dry run; pass --apply to write"))

        imported_rules = []
        totals = {"rules": 0, "accepted": 0, "rejected": 0, "duplicates": 0}

        for path in options["input"]:
            with open(path) as file:
                for line_number, line in enumerate(file, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exception:
                        self.stdout.write(
                            self.style.ERROR(
                                f"{path}:{line_number}: invalid JSON: {exception}"
                            )
                        )
                        continue

                    accepted = self.import_record(path, line_number, record, options)
                    if accepted:
                        totals["rules"] += 1
                        totals["accepted"] += accepted[0]
                        totals["rejected"] += accepted[1]
                        totals["duplicates"] += accepted[2]
                        if accepted[0] and apply:
                            imported_rules.append(record["rule_id"])

        self.stdout.write(self.style.SUCCESS(f"Totals: {totals}"))

        if imported_rules and apply:
            self.stdout.write("Re-evaluating touched rules for versioned state...")
            call_command(
                "evaluate_rules",
                rule_ids=",".join(str(pk) for pk in sorted(set(imported_rules))),
                comment="post-import evaluation (import_training_sentences)",
            )

    def import_record(self, path, line_number, record, options):
        prefix = f"{path}:{line_number}"
        rule_id = record.get("rule_id")
        try:
            rule = Rule.objects.get(pk=rule_id)
        except Rule.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"{prefix}: no rule {rule_id}"))
            return None

        sentences = record.get("sentences") or []
        negatives = record.get("negative_sentences") or []
        if not sentences:
            self.stdout.write(self.style.ERROR(f"{prefix}: no sentences"))
            return None

        payload = build_rule_payload(rule)
        existing = {
            text.strip()
            for text in TrainingSentence.objects.filter(rule=rule).values_list(
                "text", flat=True
            )
        }

        has_false_positives = rule.false_positives.exists()
        valid = []
        rejected = duplicates = 0

        for text in sentences:
            text = text.strip()
            if text in existing:
                duplicates += 1
                continue
            matched, error = evaluate_sentence(payload, text)
            if matched is None:
                self.stdout.write(
                    self.style.ERROR(f"{prefix}: #{rule.pk} API error: {error}")
                )
                rejected += 1
            elif not matched:
                self.stdout.write(
                    self.style.WARNING(
                        f"{prefix}: #{rule.pk} {rule.lemma!r}: positive sentence "
                        f"does not trigger the rule, rejected: {text[:80]!r}"
                    )
                )
                rejected += 1
            else:
                valid.append((text, False))

        near_miss = False
        for text in negatives:
            text = text.strip()
            if text in existing:
                duplicates += 1
                continue
            matched, error = evaluate_sentence(payload, text)
            if matched is None:
                self.stdout.write(
                    self.style.ERROR(f"{prefix}: #{rule.pk} API error: {error}")
                )
                rejected += 1
                continue
            if matched:
                self.stdout.write(
                    self.style.WARNING(
                        f"{prefix}: #{rule.pk} {rule.lemma!r}: negative sentence "
                        f"DOES trigger the rule, rejected: {text[:80]!r}"
                    )
                )
                rejected += 1
                continue
            if self.contains_rule_word(rule, text):
                near_miss = True
            valid.append((text, True))

        if has_false_positives and negatives and not near_miss:
            self.stdout.write(
                self.style.WARNING(
                    f"{prefix}: #{rule.pk} {rule.lemma!r}: rule has a "
                    "false-positive list but no negative contains the rule "
                    "word (near-miss required)"
                )
            )
            if not options["lenient"]:
                return (0, rejected + len(valid), duplicates)

        if rejected and not options["lenient"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{prefix}: #{rule.pk} {rule.lemma!r}: {rejected} rejected, "
                    "skipping whole rule (use --lenient to keep the valid ones)"
                )
            )
            return (0, rejected + len(valid), duplicates)

        if options["apply"]:
            for text, is_false_positive in valid:
                TrainingSentence(
                    rule=rule, text=text, is_false_positive=is_false_positive
                ).save()
        for text, is_false_positive in valid:
            polarity = "negative" if is_false_positive else "positive"
            self.stdout.write(f"+ #{rule.pk} {polarity}: {text[:80]!r}")

        return (len(valid), rejected, duplicates)

    def contains_rule_word(self, rule, text):
        """Near-miss check: the negative must contain the rule's word(s) so it
        exercises the ambiguity instead of being trivially unrelated."""
        try:
            _, tokens = analyze_text(str(rule.language), text, detailed=False)
        except Exception:
            return False

        sentence_words = {
            token.get("text", "").lower() for token in tokens
        } | {token.get("lemma", "").lower() for token in tokens}

        for rule_token in rule.lemma_json or []:
            if rule_token.lower() in sentence_words:
                return True

        return False
