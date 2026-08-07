import json

from django.core.management.base import BaseCommand, CommandError

from rules.evaluation import build_rule_payload, evaluate_sentence
from rules.models import (
    Alternative,
    FalsePositive,
    Lemmatization,
    Rule,
    RuleDiversityDimension,
    TrainingSentence,
)


class Command(BaseCommand):
    help = (
        "Apply the corrections proposed by triage_failures, following the "
        "codebase's precedents: empty the word type for marked content words "
        "(guru), create sibling rules for function words read as another POS "
        "(ninja n/a), and pin drifting surface forms in rules_lemmatization "
        "(Behinderte). Dry-run by default; idempotent; never narrows matching."
    )

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True, help="Triage JSON")
        parser.add_argument("--apply", action="store_true", help="Write changes")
        parser.add_argument("--skip-rules", type=str, help="Comma separated rule ids")
        parser.add_argument(
            "--only-rules", type=str, help="Comma separated rule ids to restrict to"
        )

    def handle(self, *args, **options):
        with open(options["input"]) as file:
            report = json.load(file)

        self.apply = options["apply"]
        if not self.apply:
            self.stdout.write(self.style.WARNING("Dry run; pass --apply to write"))

        skip = set()
        if options["skip_rules"]:
            skip = {int(pk) for pk in options["skip_rules"].split(",")}
        only = None
        if options["only_rules"]:
            only = {int(pk) for pk in options["only_rules"].split(",")}

        self.touched_rules = set()
        counts = {"empty_word_type": 0, "sibling_rule": 0, "lemmatization_pin": 0,
                  "move_sentence_to_sibling": 0, "skipped": 0, "manual": 0}

        for class_name, entries in report["classes"].items():
            for entry in entries:
                if entry["rule"] in skip or (only is not None and entry["rule"] not in only):
                    counts["skipped"] += 1
                    continue

                action = entry["proposed_action"]["action"]
                if action == "empty_word_type":
                    counts[action] += self.empty_word_type(entry)
                elif action == "sibling_rule":
                    counts[action] += self.sibling_rule(entry)
                elif action == "lemmatization_pin":
                    counts[action] += self.lemmatization_pin(entry)
                elif action == "move_sentence_to_sibling":
                    counts[action] += self.move_sentence_to_sibling(entry)
                else:
                    counts["manual"] += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {counts}"))
        if self.touched_rules:
            touched = ",".join(str(pk) for pk in sorted(self.touched_rules))
            self.stdout.write(
                "Re-evaluate the touched rules: "
                f"manage.py evaluate_rules --rule-ids {touched}"
            )

    def empty_word_type(self, entry):
        """Precedent: guru (word_type ''). Only single-token rules; the safety
        rule first copies the current type into actual_word_types when the
        alternatives are grammatically adapted, so declension keeps working."""
        rule = Rule.objects.get(pk=entry["rule"])

        if not rule.word_types:
            self.stdout.write(f"= #{rule.pk} {rule.lemma!r}: word type already empty")
            return 0

        if len(rule.lemma_json or []) != 1:
            self.stdout.write(
                self.style.WARNING(
                    f"! #{rule.pk} {rule.lemma!r}: multi-token rule, not emptying "
                    "word types automatically; handle manually"
                )
            )
            return 0

        base_type = rule.word_types.strip("=~-")
        needs_actual = entry["proposed_action"].get("needs_actual_word_types")
        set_actual = (
            needs_actual and not rule.actual_word_types and base_type in ("n", "v", "a")
        )

        self.stdout.write(
            f"+ #{rule.pk} {rule.lemma!r} ({rule.language}): word_types "
            f"{rule.word_types!r} -> None"
            + (f", actual_word_types -> {base_type!r}" if set_actual else "")
        )

        if self.apply:
            if set_actual:
                rule.actual_word_types = base_type
            rule.word_types = None
            rule.save()
            self.touched_rules.add(rule.pk)

        return 1

    def sibling_rule(self, entry):
        """Precedent: ninja exists as both a and n rules. The sibling copies
        alternatives/explanation and is marked for review so a human adjusts
        wording where the new reading warrants it. Failing sentences that
        exercise the new reading move over to the sibling."""
        rule = Rule.objects.get(pk=entry["rule"])
        created = 0

        if len(rule.lemma_json or []) != 1:
            self.stdout.write(
                self.style.WARNING(
                    f"! #{rule.pk} {rule.lemma!r}: multi-token rule, no automatic "
                    "sibling; handle manually"
                )
            )
            return 0

        for word_type in entry["proposed_action"].get("missing_word_types", []):
            existing = Rule.objects.filter(
                language=rule.language,
                lemma=rule.lemma,
                word_types=word_type,
                type=rule.type,
                pluralization=rule.pluralization,
                pattern=rule.pattern,
            ).first()
            if existing:
                self.stdout.write(
                    f"= #{rule.pk} {rule.lemma!r}: {word_type} sibling exists (#{existing.pk})"
                )
                continue

            self.stdout.write(
                f"+ #{rule.pk} {rule.lemma!r} ({rule.language}): create {word_type} sibling"
            )
            created += 1

            if not self.apply:
                continue

            sibling = Rule(
                language=rule.language,
                lemma=rule.lemma,
                word_types=word_type,
                type=rule.type,
                entity_type=rule.entity_type,
                pluralization=rule.pluralization,
                pattern=rule.pattern,
                is_pattern_match=rule.is_pattern_match,
                text_id=rule.text_id,
                label=rule.label,
                label_type=rule.label_type,
                explanation=rule.explanation,
                url=rule.url,
                emoji=rule.emoji,
                is_hr_rule=rule.is_hr_rule,
                is_context_aware=rule.is_context_aware,
                source=rule.source,
                is_active=rule.is_active,
                is_marked_for_review=True,
                comment=(
                    f"Sibling of rule {rule.pk} for the {word_type} reading; "
                    "created by apply_corrections, review alternatives"
                ),
            )
            sibling.save()

            for alternative in (
                rule.parent.alternatives if rule.parent else rule.alternatives
            ).all().order_by("order"):
                Alternative(
                    rule=sibling,
                    lemma=alternative.lemma,
                    word_types=alternative.word_types,
                    type=alternative.type,
                    pluralization=alternative.pluralization,
                    is_remove=alternative.is_remove,
                    is_inspiration=alternative.is_inspiration,
                    is_advanced=alternative.is_advanced,
                    is_collective_noun=alternative.is_collective_noun,
                    is_gendered_noun=alternative.is_gendered_noun,
                    label=alternative.label,
                    order=alternative.order,
                    is_active=alternative.is_active,
                ).save()

            for false_positive in rule.false_positives.all():
                FalsePositive.objects.create(
                    rule=sibling, false_positive=false_positive.false_positive
                )

            for through in RuleDiversityDimension.objects.filter(rule=rule):
                RuleDiversityDimension.objects.create(
                    rule=sibling,
                    diversity_dimension=through.diversity_dimension,
                    order=through.order,
                )
            # Recompute diversity_dimension_json from the copied M2M rows.
            sibling.save()

            moved = 0
            for sentence_entry in entry["sentences"]:
                token = sentence_entry.get("token")
                if token and token.get("word_type") == word_type:
                    for sentence in TrainingSentence.objects.filter(
                        rule=rule, text=sentence_entry["text"]
                    ):
                        sentence.rule = sibling
                        sentence.save()
                        moved += 1
            if moved:
                self.stdout.write(
                    f"  moved {moved} training sentence(s) exercising the "
                    f"{word_type} reading to sibling #{sibling.pk}"
                )

            self.touched_rules.add(rule.pk)
            self.touched_rules.add(sibling.pk)

        return created

    def move_sentence_to_sibling(self, entry):
        """The observed reading is already declared by an active sibling rule;
        the failing sentence simply exercises that sibling's reading."""
        rule = Rule.objects.get(pk=entry["rule"])
        moved = 0

        for sentence_entry in entry["sentences"]:
            token = sentence_entry.get("token")
            if not token:
                continue
            observed = token.get("word_type")
            if observed not in entry["proposed_action"]["word_types"]:
                continue

            sibling = (
                Rule.objects.filter(
                    language=rule.language, lemma=rule.lemma, is_active=True
                )
                .exclude(pk=rule.pk)
                .filter(word_types__in=[observed, f"~{observed}", f"-{observed}", f"={observed}"])
                .first()
            )
            if sibling is None:
                continue

            self.stdout.write(
                f"+ #{rule.pk} {rule.lemma!r}: move sentence to {observed} "
                f"sibling #{sibling.pk}: {sentence_entry['text'][:60]!r}"
            )
            if self.apply:
                # Per-object save so the computed has_training_sentences on
                # both rules is recomputed; .update() would bypass it.
                for sentence in TrainingSentence.objects.filter(
                    rule=rule, text=sentence_entry["text"]
                ):
                    sentence.rule = sibling
                    sentence.save()
                    moved += 1
                self.touched_rules.add(rule.pk)
                self.touched_rules.add(sibling.pk)
            else:
                moved += 1

        return moved

    def lemmatization_pin(self, entry):
        """Precedent: the identity pins like Behinderte->Behinderte. Pin the
        drifting surface form to the rule key so any tagger's lemma is
        overridden deterministically. The pin must prove itself before it is
        written: injected into the rule's payload it has to turn at least one
        failing sentence into a match."""
        pin = entry["proposed_action"]["pin"]

        if not self.pin_fixes_a_sentence(entry, pin):
            self.stdout.write(
                self.style.WARNING(
                    f"! pin {pin['text']!r} -> {pin['lemma']!r} does not fix any "
                    f"failing sentence of rule #{entry['rule']}; skipping"
                )
            )
            return 0

        existing = Lemmatization.objects.filter(
            language=pin["language"], text=pin["text"], word_type=""
        ).first()
        if existing:
            if existing.lemma != pin["lemma"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"! pin {pin['text']!r} exists with lemma {existing.lemma!r}, "
                        f"wanted {pin['lemma']!r}; resolve manually"
                    )
                )
            else:
                self.stdout.write(f"= pin {pin['text']!r} -> {pin['lemma']!r} exists")
            return 0

        self.stdout.write(
            f"+ pin ({pin['language']}) {pin['text']!r} -> {pin['lemma']!r}"
            + (" [plural]" if pin.get("is_plural") else "")
        )

        if self.apply:
            Lemmatization.objects.create(
                language=pin["language"],
                text=pin["text"],
                lemma=pin["lemma"],
                word_type="",
                is_plural=bool(pin.get("is_plural")),
                comment=f"Pinned by apply_corrections for rule {entry['rule']}",
            )
            self.touched_rules.add(entry["rule"])

        return 1

    def pin_fixes_a_sentence(self, entry, pin):
        rule = Rule.objects.get(pk=entry["rule"])
        payload = build_rule_payload(rule)
        payload["lemmatizations"] = payload["lemmatizations"] + [
            {"text": pin["text"], "lemma": pin["lemma"], "word_type": ""}
        ]
        for sentence_entry in entry["sentences"]:
            matched, _ = evaluate_sentence(payload, sentence_entry["text"])
            if matched:
                return True
        return False
