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
from rules.export_utils import load_json, validate_foreign_keys_exist

# Maps every FK field name to the model label it references.
# Used by _remap_foreign_keys to translate old PKs to new ones when --ignore-pk is set.
FK_FIELD_TO_MODEL = {
    "rule": RULE,
    "rule_translation_source": RULE,
    "parent": RULE,
    "diversity_dimension": DIV_DIM,
    "category": CATEGORY,
    "source": SOURCE,
    "createdby": AUTH_USER,
    "ownedby": AUTH_USER,
}

# Unique field combinations used to detect duplicates and build queries
from rules.model_constants import RULE_DIV_DIM

UNIQUE_FIELDS_MAP = {
    CATEGORY: ["name"],
    DIV_DIM: ["name"],
    SOURCE: ["name"],
    RULE: ["language", "lemma", "word_types", "type", "pluralization", "pattern"],
    RULE_DIV_DIM: [FIELD_RULE, "diversity_dimension"],
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

# Fields that never take part in identity or content comparison: user refs
# are nulled on export, timestamps change on every save.
COMPARISON_IGNORED_FIELDS = {FIELD_CREATEDBY, FIELD_OWNEDBY, "created_at", "updated_at"}

# (Import order and user-ref models provided by shared constants)


class _ImportAborted(Exception):
    """Raised inside the outer transaction to roll back the entire import."""


class Command(BaseCommand):
    help = """
    Import rules database from JSON fixture.
    The entire import runs in a single transaction; any error or unresolved
    conflict rolls the whole import back unless --allow-partial is passed.

    A record is only treated as "the same record" when its natural keys match
    (or, for models without natural keys, when its content is identical).
    A pk collision with different content is a conflict that must be resolved
    manually: --ignore-pk switches to content identity, --force-pk-overwrite
    declares the two databases share pk lineage.

    Default behaviour for same-identity records: overwrite with imported data.
    Use --skip-existing to leave them untouched, or --merge to update only
    the fields present in the import file.
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
            "--ignore-pk",
            action="store_true",
            help="Ignore primary keys from import file and generate new ones (prevents PK conflicts)",
        )
        parser.add_argument(
            "--force-pk-overwrite",
            action="store_true",
            help="Trust pk lineage: overwrite/merge records whose pk matches even "
            "when their natural keys differ (same-lineage sync only, e.g. "
            "production -> development of the SAME installation)",
        )
        parser.add_argument(
            "--allow-partial",
            action="store_true",
            help="Commit successfully imported records even when other records "
            "errored or conflicted. Default: any error or conflict rolls back "
            "the entire import so the database is never left half-updated",
        )

    # ---------------------------
    # Helper methods
    # ---------------------------

    def unique_fields(self, model_name):
        return UNIQUE_FIELDS_MAP.get(model_name, [])

    def build_unique_query(self, model_name, fields):
        """Build a queryset filter dict based on the model's unique fields.

        None values are matched with __isnull instead of aborting: most rules
        legitimately have word_types=None and pattern=None, and bailing out
        here used to disable duplicate detection for exactly those rules
        (--ignore-pk then silently created duplicates). Only a *missing* key
        means the file cannot identify the record.
        """
        uf = self.unique_fields(model_name)
        if not uf:
            return {}
        query = {}
        for f in uf:
            if f not in fields:
                return {}
            v = fields[f]
            if v is None:
                query[f"{f}__isnull"] = True
            else:
                query[f] = v
        return query

    def get_unique_identifier(self, model_name, fields):
        """Create a stable hash from the model's unique fields for duplicate detection."""
        uf = self.unique_fields(model_name)
        if not uf:
            return None
        values = []
        for f in uf:
            if f not in fields:
                return None
            values.append(f"{f}:{fields[f]!r}")
        identifier = "|".join(values)
        return hashlib.sha256(identifier.encode()).hexdigest()

    def matches_unique_fields(self, model_name, existing, fields):
        """True when the existing object and the imported fields agree on the
        model's unique (natural-key) fields; None when the model has no
        unique fields to compare."""
        uf = self.unique_fields(model_name)
        if not uf:
            return None
        for f in uf:
            existing_value = getattr(existing, f"{f}_id", getattr(existing, f, None))
            import_value = fields.get(f)
            if existing_value != import_value:
                return False
        return True

    def differing_fields(self, existing, fields):
        """Full-field comparison for models without natural keys. Returns the
        names of imported fields whose values differ from the stored record;
        an empty list means the record is identical and a re-import of the
        same file stays idempotent."""
        serialized = json.loads(serializers.serialize("json", [existing]))[0]
        existing_fields = serialized.get("fields", {})
        differing = []
        for key, import_value in fields.items():
            if key in COMPARISON_IGNORED_FIELDS:
                continue
            if existing_fields.get(key) != import_value:
                differing.append(
                    f"{key}: {existing_fields.get(key)!r} != {import_value!r}"
                )
        return differing

    def _assign_user_fields(self, fields, assign_user):
        if not assign_user:
            return
        for key in (FIELD_CREATEDBY, FIELD_OWNEDBY):
            if key in fields:
                fields[key] = assign_user.id

    def _remap_foreign_keys(self, fields, pk_mapping):
        """Translate source-installation FK pks to local pks.

        Returns the field names that could NOT be remapped (excluding user
        references, which exports null and --assign-to sets deliberately).
        Under --ignore-pk an unmapped FK still carries the source pk; saving
        it would attach the record to whatever local object happens to own
        that number - silent corruption - so callers refuse those items.
        """
        unmapped = []
        for field_name, fk_model in FK_FIELD_TO_MODEL.items():
            if field_name not in fields or fields[field_name] is None:
                continue
            mapped = pk_mapping.get(f"{fk_model}:{fields[field_name]}")
            if mapped is not None:
                fields[field_name] = mapped
            elif fk_model != AUTH_USER:
                unmapped.append(field_name)
        return unmapped

    def _merge_into_existing(self, existing, fields):
        """Copy imported field values onto the existing object, respecting
        the ORM: FK columns are set through their *_id attribute and
        many-to-many fields are left alone (they are not part of the fixture
        contract). Naive setattr(existing, 'rule', 5) raises and used to turn
        every merge of a child record into an import error."""
        model_fields = {f.name: f for f in existing._meta.get_fields()}
        for field, value in fields.items():
            model_field = model_fields.get(field)
            if model_field is None:
                continue
            if getattr(model_field, "many_to_many", False):
                continue
            if model_field.is_relation:
                setattr(existing, f"{field}_id", value)
            else:
                setattr(existing, field, value)
        existing.save()

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
        self,
        item,
        model_name,
        ignore_pk,
        pk_mapping,
        skip_existing,
        merge,
        stats,
        force_pk_overwrite=False,
    ):
        """Import a single item and update stats."""
        original_pk = item.get("pk")
        model = item.get("model")
        fields = item.get("fields")

        # Remap foreign keys if we're ignoring PKs
        if ignore_pk:
            unmapped = self._remap_foreign_keys(fields, pk_mapping)
            if unmapped:
                # The referenced object is not part of this import (or itself
                # failed). Refuse rather than attach to an arbitrary local
                # record that happens to carry the source pk.
                self.stdout.write(
                    self.style.WARNING(
                        f"  Refused {model} pk={original_pk}: references "
                        f"{', '.join(unmapped)} not contained in this import; "
                        "include the referenced record(s) in the export or "
                        "import them first"
                    )
                )
                stats["conflicts"] += 1
                return

        # Deserialize object
        obj_data = json.dumps([item])
        # Each item gets its own savepoint so an IntegrityError doesn't
        # invalidate the outer transaction for subsequent records.
        try:
            with transaction.atomic():
                objects = list(serializers.deserialize("json", obj_data))
                if not objects:
                    return

                obj = objects[0].object

                # SQLite defers FK checks to the outer COMMIT; validate now so
                # a dangling reference is this record's error, not a crash of
                # the entire import at the very end.
                validate_foreign_keys_exist(obj)

                # Check if exists
                model_class = obj.__class__

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

                    # A pk hit does not prove identity: another installation's
                    # export can carry the same pk for an unrelated record.
                    # Only treat it as the same record when the natural keys
                    # agree (or, for models without natural keys, when the
                    # content is identical - that keeps re-imports of the
                    # same file idempotent). Anything else is a conflict the
                    # operator must resolve (--ignore-pk for content identity,
                    # --force-pk-overwrite to trust pk lineage).
                    # --skip-existing never writes, so an identity mismatch
                    # cannot corrupt anything; the record is simply left alone.
                    if existing is not None and not skip_existing:
                        detail = ""
                        same = self.matches_unique_fields(
                            model_name, existing, fields
                        )
                        if same is None:
                            differing = self.differing_fields(existing, fields)
                            if not differing:
                                stats["skipped"] += 1
                                return
                            same = False
                            detail = f" (differs: {'; '.join(differing[:3])})"
                        if not same and not force_pk_overwrite:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  Conflict {model} pk={original_pk}: a "
                                    "local record with this pk has different "
                                    f"content (local: {str(existing)[:60]!r})"
                                    f"{detail}. Refusing to overwrite; use "
                                    "--ignore-pk (content identity) or "
                                    "--force-pk-overwrite (trust pk lineage)"
                                )
                            )
                            stats["conflicts"] += 1
                            return

                if existing:
                    if skip_existing:
                        stats["skipped"] += 1
                        # Still track PK mapping for foreign keys
                        self._record_pk_mapping(
                            pk_mapping, model_name, original_pk, existing.pk
                        )
                    elif merge:
                        self._merge_into_existing(existing, fields)
                        stats["updated"] += 1
                        self._record_pk_mapping(
                            pk_mapping, model_name, original_pk, existing.pk
                        )
                    else:
                        # Overwrite the record (identity established above).
                        # The deserialized object still counts as "adding";
                        # left that way, models that run full_clean() in
                        # save() (Rule, Alternative) reject their own pk as
                        # a duplicate.
                        obj.pk = existing.pk
                        obj._state.adding = False
                        obj.save()
                        stats["updated"] += 1
                        self._record_pk_mapping(
                            pk_mapping, model_name, original_pk, existing.pk
                        )
                else:
                    # Create new object
                    obj.save()
                    stats["created"] += 1
                    self._record_pk_mapping(
                        pk_mapping, model_name, original_pk, obj.pk
                    )

        except IntegrityError as e:
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
        force_pk_overwrite=False,
    ):
        """Process all items for a single model."""
        self.stdout.write(f"\nProcessing {len(items)} {model_name} objects...")

        if model_name == RULE:
            items = self._sort_rules_before_dependents(items)

        # Assign user ownership if requested (for all models with user references)
        if assign_user and model_name in MODELS_WITH_USER_REFS:
            for item in items:
                self._assign_user_fields(item["fields"], assign_user)

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
                force_pk_overwrite=force_pk_overwrite,
            )

        self.stdout.write(f"  ✓ Imported {model_name}")

    def _sort_rules_before_dependents(self, items):
        """Order rule items so parents (and translation sources) come before
        the rules that reference them. File order is not guaranteed to do
        this, and both the FK validation and --ignore-pk remapping process
        items strictly in sequence."""
        by_pk = {item.get("pk"): item for item in items}
        ordered = []
        visiting = set()
        placed = set()

        def place(item):
            pk = item.get("pk")
            if pk in placed or pk in visiting:
                return
            visiting.add(pk)
            fields = item.get("fields", {})
            for ref in ("parent", "rule_translation_source"):
                ref_pk = fields.get(ref)
                if ref_pk is not None and ref_pk in by_pk:
                    place(by_pk[ref_pk])
            visiting.discard(pk)
            placed.add(pk)
            ordered.append(item)

        for item in items:
            place(item)
        return ordered

    def _print_summary(self, stats, ignore_pk, pk_mapping, assign_user):
        """Print import summary and recommendations."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("\nImport Summary:"))
        self.stdout.write(f'  Created: {stats["created"]}')
        self.stdout.write(f'  Updated: {stats["updated"]}')
        self.stdout.write(f'  Skipped: {stats["skipped"]}')
        if stats.get("conflicts"):
            self.stdout.write(
                self.style.WARNING(f'  Conflicts (refused): {stats["conflicts"]}')
            )
        if stats["errors"] > 0:
            self.stdout.write(self.style.ERROR(f'  Errors: {stats["errors"]}'))

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
                "\n⚠ These records will be REFUSED and the import rolled back "
                "unless you choose an identity model:"
            )
            self.stdout.write(
                "  --ignore-pk           treat content as identity (generates new pks)"
            )
            self.stdout.write(
                "  --force-pk-overwrite  trust pk lineage (same-installation sync only)\n"
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
            "conflicts": 0,
            "errors": 0,
        }

        # PK remapping for foreign keys (when using --ignore-pk)
        pk_mapping = {}

        # Process each model in order inside a single transaction. Unless
        # --allow-partial is passed, any error or refused conflict rolls the
        # whole import back: a half-applied import is worse than none, and
        # the operator gets the full report either way.
        rolled_back = False
        try:
            with transaction.atomic():
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
                        force_pk_overwrite=options["force_pk_overwrite"],
                    )

                if (stats["errors"] or stats["conflicts"]) and not options[
                    "allow_partial"
                ]:
                    raise _ImportAborted()
        except _ImportAborted:
            rolled_back = True

        # Print summary
        self._print_summary(stats, ignore_pk, pk_mapping, assign_user)

        if rolled_back:
            self.stdout.write(
                self.style.ERROR(
                    f"\n✗ Import ROLLED BACK: {stats['errors']} error(s) and "
                    f"{stats['conflicts']} conflict(s). Nothing was changed. "
                    "Resolve the reported records, or pass --allow-partial to "
                    "commit the clean records anyway."
                )
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("\n✓ Import completed"))
        if stats["conflicts"] and options["allow_partial"]:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠ {stats['conflicts']} conflicting record(s) were left "
                    "untouched and need manual resolution"
                )
            )
