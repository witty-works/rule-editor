"""
Import rules database from JSON fixture.
This allows loading shared rules into a fresh installation.
"""

from django.core.management.base import BaseCommand
from django.core import serializers
from django.db import transaction, IntegrityError
from django.contrib.auth.models import User
from collections import defaultdict
import json
import hashlib

try:
    from tqdm import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Shared constants to avoid duplication of literal strings
# ---------------------------------------------------------------------------
from rules.model_constants import (
    CATEGORY,
    DIV_DIM,
    SOURCE,
    RULE,
    ALTERNATIVE,
    TRAINING_SENTENCE,
    FALSE_POSITIVE,
    LEMMATIZATION,
    EN_NOUN,
    EN_VERB,
    EN_ADJ,
    DE_NOUN,
    DE_VERB,
    DE_ADJ,
    FR_NOUN,
    AUTH_USER,
    FIELD_RULE,
    FIELD_CREATEDBY,
    FIELD_OWNEDBY,
    IMPORT_ORDER,
    MODELS_WITH_USER_REFS,
)
from rules.export_utils import load_json

# Unique field combinations used to detect duplicates and build queries
UNIQUE_FIELDS_MAP = {
    CATEGORY: ["name"],
    DIV_DIM: ["name"],
    SOURCE: ["name"],
    RULE: ["language", "lemma", "word_types", "type", "pluralization", "pattern"],
    ALTERNATIVE: [FIELD_RULE, "lemma"],
    TRAINING_SENTENCE: [FIELD_RULE, "text"],
    FALSE_POSITIVE: [FIELD_RULE, "false_positive"],
    LEMMATIZATION: ["language", "text", "word_type"],
    EN_NOUN: ["base_form"],
    EN_VERB: ["base_form"],
    EN_ADJ: ["base_form"],
    DE_NOUN: ["base_form"],
    DE_VERB: ["base_form"],
    DE_ADJ: ["base_form"],
    FR_NOUN: ["base_form"],
}

# (Import order and user-ref models provided by shared constants)


class Command(BaseCommand):
    help = """
    Import rules database from JSON fixture.
    Loads rules and related data while handling conflicts intelligently.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--input", type=str, required=True, help="Input JSON file path"
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip objects that already exist (based on unique constraints)",
        )
        parser.add_argument(
            "--merge",
            action="store_true",
            help="Update existing objects with imported data",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing records instead of inserting new ones (alias for --merge)",
        )
        parser.add_argument(
            "--assign-to",
            type=str,
            help="Assign all imported rules to specific username",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show detailed analysis of what would be imported without making changes",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Batch size for bulk operations (default: 100)",
        )
        parser.add_argument(
            "--ignore-pk",
            action="store_true",
            help="Ignore primary keys from import file and generate new ones (prevents PK conflicts)",
        )

    # ---------------------------
    # Helper methods
    # ---------------------------

    def unique_fields(self, model_name):
        return UNIQUE_FIELDS_MAP.get(model_name, [])

    def build_unique_query(self, model_name, fields):
        """Build a queryset filter dict based on the model's unique fields."""
        uf = self.unique_fields(model_name)
        if not uf:
            return {}
        query = {}
        for f in uf:
            v = fields.get(f)
            if v is None:
                return {}
            query[f] = v
        return query

    def get_unique_identifier(self, model_name, fields):
        """Create a stable hash from the model's unique fields for duplicate detection."""
        uf = self.unique_fields(model_name)
        if not uf:
            return None
        values = []
        for f in uf:
            v = fields.get(f)
            if v is None:
                return None
            values.append(f"{f}:{v}")
        identifier = "|".join(values)
        return hashlib.sha256(identifier.encode()).hexdigest()

    def _assign_user_fields(self, fields, assign_user):
        if not assign_user:
            return
        for key in (FIELD_CREATEDBY, FIELD_OWNEDBY):
            if key in fields:
                fields[key] = assign_user.id

    def _remap_foreign_keys(self, fields, pk_mapping):
        if not pk_mapping:
            return
        for field_name in (FIELD_RULE, FIELD_CREATEDBY, FIELD_OWNEDBY):
            if field_name in fields:
                fk_model = RULE if field_name == FIELD_RULE else AUTH_USER
                mapped = pk_mapping.get(f"{fk_model}:{fields[field_name]}")
                if mapped is not None:
                    fields[field_name] = mapped

    def _record_pk_mapping(self, pk_mapping, model_name, original_pk, new_pk):
        pk_key = f"{model_name}:{original_pk}"
        pk_mapping[pk_key] = new_pk

    def _find_existing(self, model_class, original_pk, model_name, fields, ignore_pk):
        """Find an existing object either by PK or by unique fields when ignoring PKs."""
        if not ignore_pk:
            try:
                return model_class.objects.get(pk=original_pk)
            except model_class.DoesNotExist:
                return None
        # When ignoring PK, try to find by unique fields
        query = self.build_unique_query(model_name, fields)
        if not query:
            return None
        return model_class.objects.filter(**query).first()

    def _load_json_data(self, input_file):
        """Load and validate JSON data from file with automatic decompression."""
        self.stdout.write(self.style.NOTICE(f"Loading data from {input_file}..."))

        try:
            data = load_json(input_file)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {input_file}"))
            return None
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"Invalid JSON: {e}"))
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error loading file: {e}"))
            return None

        self.stdout.write(f"Loaded {len(data)} objects")
        return data

    def _group_by_model(self, data):
        """Group import items by model type."""
        by_model = {}
        for item in data:
            model_name = item["model"]
            if model_name not in by_model:
                by_model[model_name] = []
            by_model[model_name].append(item)
        return by_model

    def _import_item(
        self, item, model_name, ignore_pk, pk_mapping, skip_existing, merge, stats
    ):
        """Import a single item and update stats."""
        original_pk = item.get("pk")
        model = item.get("model")
        fields = item.get("fields")

        # Remap foreign keys if we're ignoring PKs
        if ignore_pk and pk_mapping:
            self._remap_foreign_keys(fields, pk_mapping)

        # Deserialize object
        obj_data = json.dumps([item])
        try:
            objects = list(serializers.deserialize("json", obj_data))
            if not objects:
                return

            obj = objects[0].object

            # Check if exists
            model_class = obj.__class__
            existing = None

            if ignore_pk:
                # Check for duplicate by unique fields
                existing = self._find_existing(
                    model_class, original_pk, model_name, fields, True
                )
                # Don't use the imported PK
                obj.pk = None
            else:
                # Try to find by PK
                existing = self._find_existing(
                    model_class, original_pk, model_name, fields, False
                )

            if existing:
                if skip_existing:
                    stats["skipped"] += 1
                    # Still track PK mapping for foreign keys
                    if ignore_pk:
                        self._record_pk_mapping(
                            pk_mapping, model_name, original_pk, existing.pk
                        )
                elif merge:
                    # Update existing object
                    for field, value in fields.items():
                        if hasattr(existing, field):
                            setattr(existing, field, value)
                    existing.save()
                    stats["updated"] += 1
                    # Track PK mapping
                    if ignore_pk:
                        self._record_pk_mapping(
                            pk_mapping, model_name, original_pk, existing.pk
                        )
                else:
                    # Default: update existing
                    obj.pk = existing.pk
                    obj.save()
                    stats["updated"] += 1
                    # Track PK mapping
                    if ignore_pk:
                        self._record_pk_mapping(
                            pk_mapping, model_name, original_pk, existing.pk
                        )
            else:
                # Create new object
                obj.save()
                stats["created"] += 1
                # Track PK mapping for new objects
                if ignore_pk:
                    self._record_pk_mapping(pk_mapping, model_name, original_pk, obj.pk)

        except IntegrityError as e:
            if skip_existing:
                stats["skipped"] += 1
            else:
                self.stdout.write(self.style.WARNING(f"  Integrity error: {e}"))
                stats["errors"] += 1
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"  Error importing {model} pk={original_pk}: {e}")
            )
            stats["errors"] += 1

    def _process_model(
        self,
        model_name,
        items,
        assign_user,
        ignore_pk,
        pk_mapping,
        skip_existing,
        merge,
        stats,
    ):
        """Process all items for a single model."""
        self.stdout.write(f"\nProcessing {len(items)} {model_name} objects...")

        # Assign user ownership if requested (for all models with user references)
        if assign_user and model_name in MODELS_WITH_USER_REFS:
            for item in items:
                self._assign_user_fields(item["fields"], assign_user)

        # Import with transaction
        try:
            with transaction.atomic():
                # Use tqdm for progress bar if available
                items_iter = (
                    tqdm(items, desc=f"  {model_name}", leave=False, ncols=80)
                    if HAS_TQDM and len(items) > 100
                    else items
                )

                for item in items_iter:
                    self._import_item(
                        item,
                        model_name,
                        ignore_pk,
                        pk_mapping,
                        skip_existing,
                        merge,
                        stats,
                    )

                self.stdout.write(f"  ✓ Imported {model_name}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"  Transaction failed for {model_name}: {e}")
            )
            stats["errors"] += len(items)

    def _print_summary(self, stats, ignore_pk, pk_mapping, assign_user):
        """Print import summary and recommendations."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("\nImport Summary:"))
        self.stdout.write(f'  Created: {stats["created"]}')
        self.stdout.write(f'  Updated: {stats["updated"]}')
        self.stdout.write(f'  Skipped: {stats["skipped"]}')
        if stats["errors"] > 0:
            self.stdout.write(self.style.ERROR(f'  Errors: {stats["errors"]}'))

        self.stdout.write(self.style.SUCCESS("\n✓ Import completed"))

        if ignore_pk:
            self.stdout.write(
                self.style.NOTICE(
                    f"\nPK remapping: Tracked {len(pk_mapping)} ID mappings"
                )
            )

        if assign_user:
            self.stdout.write(
                self.style.NOTICE(
                    f"\nAll rules assigned to user: {assign_user.username}"
                )
            )

        # Recommendations
        self.stdout.write("\nRecommended next steps:")
        self.stdout.write("  1. Run: python manage.py check_rules")
        self.stdout.write("  2. Verify imported data in admin interface")
        if not assign_user:
            self.stdout.write(
                "  3. Consider running: python manage.py assign_rule_ownership --username=<your_username>"
            )

    def analyze_import(self, data, assign_user=None):
        """
        Analyze what would be imported and detect duplicates.
        Returns detailed statistics and conflict information.
        """
        from django.apps import apps

        analysis = {
            "total_objects": len(data),
            "by_model": defaultdict(
                lambda: {
                    "count": 0,
                    "new": 0,
                    "pk_conflicts": 0,
                    "true_duplicates": 0,
                    "would_update": 0,
                    "samples": [],
                }
            ),
            "conflicts": [],
            "user_assignment": assign_user.username if assign_user else None,
        }

        for item in data:
            model_name = item["model"]
            pk = item.get("pk")
            fields = item["fields"]

            model_info = analysis["by_model"][model_name]
            model_info["count"] += 1

            # Try to get the model class
            try:
                app_label, model_class_name = model_name.split(".")
                model_class = apps.get_model(app_label, model_class_name)
            except (ValueError, LookupError):
                continue

            # Check if PK exists
            existing_obj = None
            try:
                existing_obj = model_class.objects.get(pk=pk)
            except model_class.DoesNotExist:
                existing_obj = None

            # Get unique identifier
            unique_id = self.get_unique_identifier(model_name, fields)

            if existing_obj:
                # Compare using unique fields when available
                check_fields = self.unique_fields(model_name)
                if unique_id and check_fields:
                    is_same = True
                    for field in check_fields:
                        existing_value = getattr(existing_obj, field, None)
                        import_value = fields.get(field)
                        if hasattr(existing_value, "id"):
                            existing_value = existing_value.id
                        if existing_value != import_value:
                            is_same = False
                            break
                    if is_same:
                        model_info["true_duplicates"] += 1
                    else:
                        model_info["pk_conflicts"] += 1
                        analysis["conflicts"].append(
                            {
                                "model": model_name,
                                "pk": pk,
                                "reason": "PK exists but data differs",
                                "existing": str(existing_obj)[:100],
                                "import_summary": f"{fields.get('lemma', fields.get('name', 'N/A'))}",
                            }
                        )
                else:
                    model_info["would_update"] += 1
            else:
                model_info["new"] += 1

            # Store sample records (first 3 of each model)
            if len(model_info["samples"]) < 3:
                sample = {"pk": pk}
                # Add relevant fields for display
                for field in [
                    "name",
                    "lemma",
                    "trigger",
                    "language",
                    "word",
                    "sentence",
                ]:
                    if field in fields:
                        sample[field] = fields[field]
                model_info["samples"].append(sample)

        return analysis

    def print_analysis(self, analysis):
        """Print detailed dry-run analysis."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("IMPORT ANALYSIS"))
        self.stdout.write("=" * 80 + "\n")

        self.stdout.write(f"Total objects in import file: {analysis['total_objects']}")

        if analysis["user_assignment"]:
            self.stdout.write(
                self.style.NOTICE(
                    f"All imported data will be assigned to user: {analysis['user_assignment']}"
                )
            )

        self.stdout.write("\n" + "-" * 80)
        self.stdout.write("BREAKDOWN BY MODEL:")
        self.stdout.write("-" * 80 + "\n")

        # Sort models by count
        sorted_models = sorted(
            analysis["by_model"].items(), key=lambda x: x[1]["count"], reverse=True
        )

        total_new = 0
        total_conflicts = 0
        total_duplicates = 0

        for model_name, info in sorted_models:
            total_new += info["new"]
            total_conflicts += info["pk_conflicts"]
            total_duplicates += info["true_duplicates"]

            self.stdout.write(f"\n{model_name}:")
            self.stdout.write(f"  Total in import:     {info['count']}")

            if info["new"] > 0:
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ New records:       {info['new']}")
                )

            if info["true_duplicates"] > 0:
                self.stdout.write(
                    f"  ≈ True duplicates:   {info['true_duplicates']} (identical data, will skip)"
                )

            if info["pk_conflicts"] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ PK conflicts:      {info['pk_conflicts']} (same PK, different data)"
                    )
                )

            if info["would_update"] > 0:
                self.stdout.write(f"  ↻ Would update:      {info['would_update']}")

            # Show samples
            if info["samples"]:
                self.stdout.write("  Samples:")
                for sample in info["samples"]:
                    sample_str = f"    PK={sample['pk']}"
                    for k, v in sample.items():
                        if k != "pk" and v:
                            sample_str += f", {k}={str(v)[:50]}"
                    self.stdout.write(sample_str)

        # Summary
        self.stdout.write("\n" + "-" * 80)
        self.stdout.write("SUMMARY:")
        self.stdout.write("-" * 80 + "\n")

        self.stdout.write(
            self.style.SUCCESS(f"Would create:        {total_new} new records")
        )

        if total_duplicates > 0:
            self.stdout.write(
                f"Would skip:          {total_duplicates} true duplicates"
            )

        if total_conflicts > 0:
            self.stdout.write(
                self.style.WARNING(f"PK conflicts found:  {total_conflicts} records")
            )
            self.stdout.write(
                "\n⚠ RECOMMENDATION: Use --ignore-pk flag to avoid PK conflicts"
            )
            self.stdout.write(
                "  This will generate new PKs and detect duplicates by content instead\n"
            )

        # Show conflicts details
        if analysis["conflicts"]:
            self.stdout.write("\n" + "-" * 80)
            self.stdout.write(self.style.WARNING("PK CONFLICTS DETAIL:"))
            self.stdout.write("-" * 80 + "\n")

            for conflict in analysis["conflicts"][:10]:
                self.stdout.write(f"\n{conflict['model']} PK={conflict['pk']}:")
                self.stdout.write(f"  Reason: {conflict['reason']}")
                self.stdout.write(f"  Existing: {conflict['existing']}")
                self.stdout.write(f"  Import: {conflict['import_summary']}")

            if len(analysis["conflicts"]) > 10:
                self.stdout.write(
                    f"\n... and {len(analysis['conflicts']) - 10} more conflicts"
                )

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(
            self.style.NOTICE("This was a DRY RUN - no changes were made")
        )
        self.stdout.write("=" * 80 + "\n")

        self.stdout.write("\nTO PROCEED:")
        self.stdout.write("  • Remove --dry-run flag to perform the import")
        if total_conflicts > 0:
            self.stdout.write(
                "  • Add --ignore-pk to generate new PKs and avoid conflicts"
            )
        self.stdout.write("  • Add --skip-existing to skip duplicates")
        self.stdout.write("  • Add --merge to update existing records")

    def handle(self, *args, **options):
        input_file = options["input"]
        skip_existing = options["skip_existing"]
        merge = options["merge"]
        update = options.get("update", False)
        assign_to = options["assign_to"]
        dry_run = options["dry_run"]
        ignore_pk = options["ignore_pk"]

        # --update is an alias for --merge
        if update:
            merge = True

        # Validate assign_to user if provided
        assign_user = None
        if assign_to:
            try:
                assign_user = User.objects.get(username=assign_to)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f'User "{assign_to}" not found. Create user first.'
                    )
                )
                return

        # Load JSON data
        data = self._load_json_data(input_file)
        if data is None:
            return

        # Dry run - show detailed analysis
        if dry_run:
            analysis = self.analyze_import(data, assign_user)
            self.print_analysis(analysis)
            return

        self.stdout.write(self.style.WARNING("\nStarting import..."))
        if ignore_pk:
            self.stdout.write(
                self.style.NOTICE(
                    "--ignore-pk: Will generate new PKs and detect duplicates by content"
                )
            )

        # Group by model
        by_model = self._group_by_model(data)

        # Import statistics
        stats = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }

        # PK remapping for foreign keys (when using --ignore-pk)
        pk_mapping = {}

        # Process each model in order
        for model_name in IMPORT_ORDER:
            if model_name not in by_model:
                continue

            items = by_model[model_name]
            self._process_model(
                model_name,
                items,
                assign_user,
                ignore_pk,
                pk_mapping,
                skip_existing,
                merge,
                stats,
            )

        # Print summary
        self._print_summary(stats, ignore_pk, pk_mapping, assign_user)
