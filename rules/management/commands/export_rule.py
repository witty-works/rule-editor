"""
Export individual rule(s) with all related data to JSON.
Useful for sharing specific rules between installations.
"""

from django.core.management.base import BaseCommand
from django.core import serializers
from rules.models import (
    Rule,
    RuleDiversityDimension,
)
import json

# Shared field constants
from rules.model_constants import FIELD_CREATEDBY, FIELD_OWNEDBY
from rules.export_utils import dump_json, format_export_summary


class Command(BaseCommand):
    help = """
    Export individual rule(s) with all related data.
    This creates a portable JSON file containing the rule and its relationships.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--id", type=str, help="Rule ID(s) to export (comma-separated for multiple)"
        )
        parser.add_argument("--lemma", type=str, help="Export rules matching lemma")
        parser.add_argument(
            "--language",
            type=str,
            choices=["en", "de", "fr"],
            help="Filter by language",
        )
        parser.add_argument("--text-id", type=str, help="Export rule by text_id")
        parser.add_argument(
            "--output",
            type=str,
            default="rule_export.json",
            help="Output file path (use .json.gz for compression, default: rule_export.json)",
        )
        parser.add_argument(
            "--compress",
            action="store_true",
            help="Compress output with gzip (automatic if filename ends with .gz)",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Include all dependencies (categories, dimensions, sources)",
        )
        parser.add_argument(
            "--indent", type=int, default=2, help="JSON indentation (default: 2)"
        )

    def handle(self, *args, **options):
        rule_ids = options.get("id")
        lemma = options.get("lemma")
        language = options.get("language")
        text_id = options.get("text_id")
        output_file = options["output"]
        compress = options["compress"]
        full = options["full"]
        indent = options["indent"] if options["indent"] > 0 else None

        # Build query
        rules = Rule.objects.all()

        if rule_ids:
            ids = [int(x.strip()) for x in rule_ids.split(",")]
            rules = rules.filter(id__in=ids)

        if lemma:
            rules = rules.filter(lemma__icontains=lemma)

        if language:
            rules = rules.filter(language=language)

        if text_id:
            rules = rules.filter(text_id=text_id)

        if not rules.exists():
            self.stdout.write(self.style.ERROR("No rules found matching criteria"))
            return

        self.stdout.write(f"Found {rules.count()} rule(s) to export")

        # Collect all objects to export
        all_objects = []
        exported_ids = {
            "rules": set(),
            "alternatives": set(),
            "training_sentences": set(),
            "false_positives": set(),
            "diversity_dimensions": set(),
            "categories": set(),
            "sources": set(),
        }

        for rule in rules:
            self.stdout.write(f"  Exporting: {rule.lemma} ({rule.language})")

            # Add rule
            all_objects.append(rule)
            exported_ids["rules"].add(rule.id)

            # Add alternatives
            for alt in rule.alternatives.all():
                all_objects.append(alt)
                exported_ids["alternatives"].add(alt.id)

                # Add alternative sources
                if alt.source and alt.source.id not in exported_ids["sources"]:
                    all_objects.append(alt.source)
                    exported_ids["sources"].add(alt.source.id)

            # Add training sentences
            for ts in rule.training_sentences.all():
                all_objects.append(ts)
                exported_ids["training_sentences"].add(ts.id)

                # Add training sentence sources
                if ts.source and ts.source.id not in exported_ids["sources"]:
                    all_objects.append(ts.source)
                    exported_ids["sources"].add(ts.source.id)

            # Add false positives
            for fp in rule.false_positives.all():
                all_objects.append(fp)
                exported_ids["false_positives"].add(fp.id)

            # Add diversity dimensions relationships
            for rdd in RuleDiversityDimension.objects.filter(rule=rule):
                all_objects.append(rdd)

                if (
                    rdd.diversity_dimension.id
                    not in exported_ids["diversity_dimensions"]
                ):
                    all_objects.append(rdd.diversity_dimension)
                    exported_ids["diversity_dimensions"].add(rdd.diversity_dimension.id)

                    # Add category if in full mode
                    if full:
                        cat = rdd.diversity_dimension.category
                        if cat.id not in exported_ids["categories"]:
                            all_objects.append(cat)
                            exported_ids["categories"].add(cat.id)

            # Add rule source
            if rule.source and rule.source.id not in exported_ids["sources"]:
                all_objects.append(rule.source)
                exported_ids["sources"].add(rule.source.id)

            # Add parent rule if exists
            if rule.parent and rule.parent.id not in exported_ids["rules"]:
                self.stdout.write(f"    Including parent rule: {rule.parent.lemma}")
                all_objects.append(rule.parent)
                exported_ids["rules"].add(rule.parent.id)

            # Add linked rules
            for linked in rule.links.all():
                if linked.id not in exported_ids["rules"]:
                    self.stdout.write(f"    Including linked rule: {linked.lemma}")
                    all_objects.append(linked)
                    exported_ids["rules"].add(linked.id)

        # Serialize
        self.stdout.write(
            self.style.NOTICE(f"Serializing {len(all_objects)} objects...")
        )

        data = serializers.serialize(
            "json",
            all_objects,
            indent=indent,
            use_natural_foreign_keys=False,
        )

        # Parse and clean user references
        data_list = json.loads(data)
        for item in data_list:
            fields = item.get("fields", {})
            # Nullify user references
            for key in (FIELD_CREATEDBY, FIELD_OWNEDBY):
                if key in fields:
                    fields[key] = None

        # Write to file
        output_path = dump_json(
            data_list, output_file, indent=indent, compress=compress
        )

        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Successfully exported to {output_path}")
        )
        # Prepare summary using shared formatter
        counts = {
            "Alternatives": len(exported_ids["alternatives"]),
            "Diversity Dimensions": len(exported_ids["diversity_dimensions"]),
            "False Positives": len(exported_ids["false_positives"]),
            "Rules": len(exported_ids["rules"]),
            "Sources": len(exported_ids["sources"]),
            "Training Sentences": len(exported_ids["training_sentences"]),
        }
        if full:
            counts["Categories"] = len(exported_ids["categories"])
        summary = format_export_summary(
            counts, len(all_objects), output_file=output_path
        )
        self.stdout.write("\n" + summary)
