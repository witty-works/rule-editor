"""
Export rule database to a portable JSON fixture, excluding user data.
This allows sharing the rules database while maintaining privacy.
"""

from django.core.management.base import BaseCommand
from django.core import serializers
from django.apps import apps
import json

try:
    from tqdm import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Shared field constants
from rules.model_constants import (
    FIELD_CREATEDBY,
    FIELD_OWNEDBY,
    EXPORT_MODELS_BASE,
    EXPORT_MODELS_MAIN,
    EXPORT_MODELS_LINGUISTIC,
    EXPORT_MODELS_EVALUATIONS,
)
from rules.export_utils import dump_json, format_export_summary


class Command(BaseCommand):
    help = """
    Export rules database to JSON fixture, excluding user data.
    This creates a portable file that can be shared and imported into other installations.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="rules_export.json",
            help="Output file path (use .json.gz for compression, default: rules_export.json)",
        )
        parser.add_argument(
            "--compress",
            action="store_true",
            help="Compress output with gzip (automatic if filename ends with .gz)",
        )
        parser.add_argument(
            "--exclude-linguistic-data",
            action="store_true",
            help="Exclude linguistic declension data (English/German nouns, verbs, adjectives)",
        )
        parser.add_argument(
            "--exclude-evaluations",
            action="store_true",
            help="Exclude rule structure evaluations",
        )
        parser.add_argument(
            "--dimension",
            type=str,
            help="Export only rules from specific diversity dimension",
        )
        parser.add_argument(
            "--language",
            type=str,
            choices=["en", "de", "fr"],
            help="Export only rules for specific language",
        )
        parser.add_argument(
            "--created-after",
            type=str,
            help="Export only records created after date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--created-before",
            type=str,
            help="Export only records created before date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--updated-after",
            type=str,
            help="Export only records updated after date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--updated-before",
            type=str,
            help="Export only records updated before date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--since",
            type=str,
            help="Export only rules updated since date (YYYY-MM-DD) - alias for --updated-after",
        )
        parser.add_argument(
            "--rule-ids",
            type=str,
            help="Export specific rule IDs (comma-separated, e.g., '123,456,789')",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation (default: 2, use 0 for compact)",
        )

    def handle(self, *args, **options):
        output_file = options["output"]
        # True when --compress is explicitly passed; None otherwise so dump_json
        # can auto-detect compression from a .json.gz extension.
        compress = True if options["compress"] else None
        exclude_linguistic = options["exclude_linguistic_data"]
        exclude_evaluations = options["exclude_evaluations"]
        dimension_filter = options["dimension"]
        language_filter = options["language"]
        created_after = options.get("created_after")
        created_before = options.get("created_before")
        updated_after = options.get("updated_after")
        updated_before = options.get("updated_before")
        since_filter = options["since"]
        rule_ids_str = options.get("rule_ids")

        # Parse rule IDs if provided
        rule_ids = None
        if rule_ids_str:
            try:
                rule_ids = [
                    int(id.strip())
                    for id in rule_ids_str.split(",")
                    if id.strip().isdigit()
                ]
                if not rule_ids:
                    self.stdout.write(
                        self.style.ERROR(
                            "Invalid rule IDs format. Use comma-separated integers."
                        )
                    )
                    return
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(
                        "Invalid rule IDs format. Use comma-separated integers."
                    )
                )
                return

        # --since is an alias for --updated-after
        if since_filter and not updated_after:
            updated_after = since_filter

        indent = options["indent"] if options["indent"] > 0 else None

        self.stdout.write(self.style.NOTICE("Starting export..."))

        # Define models to export in dependency order via shared constants
        models_to_export = [*EXPORT_MODELS_BASE, *EXPORT_MODELS_MAIN]
        if not exclude_linguistic:
            models_to_export.extend(EXPORT_MODELS_LINGUISTIC)
        if not exclude_evaluations:
            models_to_export.extend(EXPORT_MODELS_EVALUATIONS)

        # Collect all objects
        all_objects = []
        exported_counts = {}

        # Helper to apply the same rule filters in one place
        def _apply_rule_filters(qs):
            if rule_ids:
                qs = qs.filter(id__in=rule_ids)
            if dimension_filter:
                qs = qs.filter(
                    diversity_dimensions__name__icontains=dimension_filter
                ).distinct()
            if language_filter:
                qs = qs.filter(language=language_filter)
            if created_after:
                qs = qs.filter(created_at__gte=created_after)
            if created_before:
                qs = qs.filter(created_at__lte=created_before)
            if updated_after:
                qs = qs.filter(updated_at__gte=updated_after)
            if updated_before:
                qs = qs.filter(updated_at__lte=updated_before)
            return qs

        filter_active = any(
            [
                rule_ids,
                dimension_filter,
                language_filter,
                created_after,
                created_before,
                updated_after,
                updated_before,
            ]
        )

        # Compute filtered rule IDs once so related-model queries don't
        # mutate the closure variable and re-trigger the filter on each model.
        filtered_rule_id_list = None
        if filter_active:
            from rules.models import Rule

            filtered_rule_id_list = list(
                _apply_rule_filters(Rule.objects.all()).values_list("id", flat=True)
            )

        for model_path in models_to_export:
            app_label, model_name = model_path.split(".")
            model = apps.get_model(app_label, model_name)

            # Order by primary key for deterministic output
            queryset = model.objects.all().order_by("pk")

            # Apply filters
            if model_name == "Rule":
                queryset = _apply_rule_filters(queryset)

            # Restrict related models to the filtered rule set
            if (
                model_name
                in [
                    "Alternative",
                    "TrainingSentence",
                    "FalsePositive",
                    "RuleDiversityDimension",
                    "RuleStructureEvaluation",
                ]
                and filter_active
            ):
                queryset = queryset.filter(rule_id__in=filtered_rule_id_list)

            count = queryset.count()
            if count > 0:
                exported_counts[model_name] = count
                self.stdout.write(f"  Collecting {count} {model_name} objects...")

                # Use tqdm for progress bar if available and count is large
                queryset_iter = (
                    tqdm(queryset, desc=f"  {model_name}", leave=False, ncols=80)
                    if HAS_TQDM and count > 100
                    else queryset
                )

                for obj in queryset_iter:
                    all_objects.append(obj)

        # Serialize to JSON
        self.stdout.write(
            self.style.NOTICE(f"Serializing {len(all_objects)} total objects...")
        )

        # Custom serializer that nullifies user references
        data = serializers.serialize(
            "json",
            all_objects,
            indent=indent,
            use_natural_foreign_keys=False,
            use_natural_primary_keys=False,
        )

        # Parse and clean user references
        data_list = json.loads(data)
        for item in data_list:
            fields = item.get("fields", {})
            # Nullify user references
            for key in (FIELD_CREATEDBY, FIELD_OWNEDBY):
                if key in fields:
                    fields[key] = None

        # Write to file (atomic) using shared utility
        output_path = dump_json(
            data_list, output_file, indent=indent, compress=compress
        )

        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Successfully exported to {output_path}")
        )
        summary = format_export_summary(
            exported_counts, len(all_objects), output_file=output_path
        )
        self.stdout.write("\n" + summary)
        self.stdout.write(
            self.style.NOTICE(
                "\nNote: User references (createdby, ownedby) have been set to null"
            )
        )

        # Include taggit tags note
        self.stdout.write(
            self.style.WARNING(
                "\nNote: Tags are exported separately by Django. "
                "If you need tags, also export: taggit.Tag, taggit.TaggedItem"
            )
        )
