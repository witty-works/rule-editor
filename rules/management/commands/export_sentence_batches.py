import json
import os

from django.core.management.base import BaseCommand

from rules.models import Rule


class Command(BaseCommand):
    help = (
        "Export rules lacking training sentences as JSONL batches for "
        "chat-driven sentence generation. Each line carries what a writer "
        "needs to produce realistic, on-intent sentences: the rule's words "
        "and word types, subcategories, pattern, alternatives summary, false "
        "positives, and the explanation of why the term is problematic. "
        "Batches are ordered: corrected rules first (pass --priority-ids or "
        "--triage-input), then any-position rules (empty word type), then the "
        "rest."
    )

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", type=str, required=True)
        parser.add_argument("--batch-size", type=int, default=50)
        parser.add_argument("--lang", type=str)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--priority-ids", type=str, help="Comma separated rule ids to export first"
        )
        parser.add_argument(
            "--triage-input",
            type=str,
            help="Triage JSON; its actionable rules become the priority set",
        )
        parser.add_argument(
            "--include-with-sentences",
            action="store_true",
            help="Also export rules that already have training sentences",
        )

    def handle(self, *args, **options):
        priority = set()
        if options["priority_ids"]:
            priority |= {int(pk) for pk in options["priority_ids"].split(",")}
        if options["triage_input"]:
            with open(options["triage_input"]) as file:
                triage = json.load(file)
            for entries in triage["classes"].values():
                for entry in entries:
                    if entry["proposed_action"]["action"] != "manual":
                        priority.add(entry["rule"])

        rules = Rule.objects.filter(is_active=True)
        if options["lang"]:
            rules = rules.filter(language=options["lang"])
        if not options["include_with_sentences"]:
            rules = rules.filter(training_sentences__isnull=True)

        def sort_key(rule):
            if rule.pk in priority:
                tier = 0
            elif not rule.word_types:
                # Any-position rules match in every POS reading, so their
                # sentences guard the widest surface; they come next.
                tier = 1
            else:
                tier = 2
            return (tier, rule.language, rule.pk)

        rules = sorted(rules.prefetch_related("alternatives", "false_positives"), key=sort_key)
        if options["limit"]:
            rules = rules[: options["limit"]]

        os.makedirs(options["output_dir"], exist_ok=True)
        batch_size = options["batch_size"]
        batch_count = 0
        for start in range(0, len(rules), batch_size):
            batch = rules[start : start + batch_size]
            batch_count += 1
            path = os.path.join(
                options["output_dir"], f"batch_{batch_count:04d}.jsonl"
            )
            with open(path, "w") as file:
                for rule in batch:
                    alternatives = [
                        {
                            "lemma": alternative.lemma,
                            "is_remove": alternative.is_remove,
                            "is_inspiration": alternative.is_inspiration,
                        }
                        for alternative in (
                            rule.parent.alternatives
                            if rule.parent
                            else rule.alternatives
                        ).all()
                    ]
                    file.write(
                        json.dumps(
                            {
                                "rule_id": rule.pk,
                                "language": str(rule.language),
                                "lemma": rule.lemma,
                                "words": rule.lemma_json,
                                "word_types": rule.word_types,
                                "word_types_json": rule.word_types_json,
                                "subcategories": rule.diversity_dimension_json,
                                "pattern": rule.pattern,
                                "pluralization": str(rule.pluralization),
                                "entity_type": str(rule.entity_type),
                                "label": rule.label,
                                "label_type": str(rule.label_type),
                                "explanation": rule.explanation,
                                "alternatives": alternatives,
                                "false_positives": [
                                    false_positive.false_positive
                                    for false_positive in rule.false_positives.all()
                                ],
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(rules)} rules into {batch_count} batches "
                f"({len(priority & {rule.pk for rule in rules})} priority) "
                f"in {options['output_dir']}"
            )
        )
        self.stdout.write(
            "Expected import format per line: "
            '{"rule_id": ..., "sentences": ["..."], "negative_sentences": ["..."]}'
        )
