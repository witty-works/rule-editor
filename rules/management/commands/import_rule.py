"""
Import individual rule(s) from JSON export.
Handles dependencies and conflicts intelligently.
"""

from django.core.management.base import BaseCommand
from django.core import serializers
from django.db import transaction
from django.contrib.auth.models import User
from rules.models import Rule, Category, DiversityDimension, Source
import json

# Shared field constants
from rules.model_constants import (
    CATEGORY,
    DIV_DIM,
    SOURCE,
    RULE,
    RULE_DIV_DIM,
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
    RULE_STRUCTURE_EVAL,
    MODELS_WITH_USER_REFS,
)
from rules.export_utils import load_json, validate_foreign_keys_exist


class Command(BaseCommand):
    help = """
    Import individual rule(s) from JSON export.
    Handles dependencies and can skip or update existing rules.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--input", type=str, required=True, help="Input JSON file path"
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip rules that already exist (matched on the full natural key: "
            "language, lemma, word_types, type, pluralization, pattern)",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing rules with imported data",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="DESTRUCTIVE: delete an existing rule (cascades to its "
            "alternatives, sentences, false positives and evaluations) and "
            "recreate it from the import. Without this flag an existing rule "
            "is skipped and reported",
        )
        parser.add_argument(
            "--allow-partial",
            action="store_true",
            help="Commit successfully imported records even when others "
            "errored. Default: any error rolls back the entire import",
        )
        parser.add_argument(
            "--owner", type=str, help="Assign imported rules to specific username"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--create-dependencies",
            action="store_true",
            help="Create missing categories and diversity dimensions",
        )

    def handle(self, *args, **options):
        input_file = options["input"]
        skip_existing = options["skip_existing"]
        update_existing = options["update_existing"]
        replace = options["replace"]
        allow_partial = options["allow_partial"]
        owner = options["owner"]
        dry_run = options["dry_run"]
        create_deps = options["create_dependencies"]

        if sum([skip_existing, update_existing, replace]) > 1:
            self.stdout.write(
                self.style.ERROR(
                    "--skip-existing, --update-existing and --replace are "
                    "mutually exclusive"
                )
            )
            return

        # Validate owner if provided
        owner_user = None
        if owner:
            try:
                owner_user = User.objects.get(username=owner)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User "{owner}" not found'))
                return

        self.stdout.write(self.style.NOTICE(f"Loading from {input_file}..."))

        # Load JSON (supports both .json and .json.gz)
        try:
            data = load_json(input_file)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {input_file}"))
            return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"Invalid JSON: {e}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error loading file: {e}"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE"))

        # Group by model
        by_model = {}
        for item in data:
            model_name = item["model"]
            if model_name not in by_model:
                by_model[model_name] = []
            by_model[model_name].append(item)

        stats = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }

        # Import order
        import_order = [
            CATEGORY,
            SOURCE,
            DIV_DIM,
            RULE,
            RULE_DIV_DIM,
            ALTERNATIVE,
            TRAINING_SENTENCE,
            FALSE_POSITIVE,
        ]

        # Track PK mapping (old PK -> new PK)
        pk_mapping = {}

        class _ImportAborted(Exception):
            pass

        # Import each model. The outer transaction makes an error roll the
        # entire import back unless --allow-partial was requested: a rule
        # without its alternatives is worse than no rule at all.
        rolled_back = False
        try:
            with transaction.atomic():
                for model_name in import_order:
                    if model_name not in by_model:
                        continue

                    items = by_model[model_name]
                    self.stdout.write(f"\n{model_name}: {len(items)} object(s)")

                    for item in items:
                        pk = item.get("pk")
                        fields = item.get("fields", {})

                        # Assign owner if requested
                        if owner_user and model_name in MODELS_WITH_USER_REFS:
                            if "createdby" in fields:
                                fields["createdby"] = owner_user.id
                            if "ownedby" in fields:
                                fields["ownedby"] = owner_user.id

                        if dry_run:
                            self.stdout.write(f"  Would import {model_name} pk={pk}")
                            stats["created"] += 1
                            continue

                        try:
                            with transaction.atomic():
                                # Handle based on model type
                                if model_name == RULE:
                                    result = self._import_rule(
                                        item, pk_mapping, update_existing, replace
                                    )
                                elif model_name == CATEGORY:
                                    result = self._import_category(item, create_deps)
                                elif model_name == DIV_DIM:
                                    result = self._import_dimension(
                                        item, pk_mapping, create_deps
                                    )
                                elif model_name == SOURCE:
                                    result = self._import_source(item)
                                else:
                                    result = self._import_generic(item, pk_mapping)

                                if result["status"] == "created":
                                    stats["created"] += 1
                                    pk_mapping[f"{model_name}:{pk}"] = result["new_pk"]
                                    self.stdout.write(
                                        f'  ✓ Created {model_name} (old pk={pk}, new pk={result["new_pk"]})'
                                    )
                                elif result["status"] == "updated":
                                    stats["updated"] += 1
                                    pk_mapping[f"{model_name}:{pk}"] = result["new_pk"]
                                    self.stdout.write(
                                        f'  ↻ Updated {model_name} pk={result["new_pk"]}'
                                    )
                                elif result["status"] == "skipped":
                                    stats["skipped"] += 1
                                    pk_mapping[f"{model_name}:{pk}"] = result[
                                        "existing_pk"
                                    ]
                                    self.stdout.write(
                                        f"  = Skipped existing {model_name} "
                                        f'pk={result["existing_pk"]} (use '
                                        "--update-existing or --replace to change it)"
                                    )
                                elif result["status"] == "error":
                                    stats["errors"] += 1
                                    self.stdout.write(
                                        self.style.ERROR(
                                            f'  ✗ Error: {result["message"]}'
                                        )
                                    )

                        except Exception as e:
                            stats["errors"] += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f"  ✗ Error importing {model_name} pk={pk}: {e}"
                                )
                            )

                if stats["errors"] and not allow_partial and not dry_run:
                    raise _ImportAborted()
        except _ImportAborted:
            rolled_back = True

        # Print summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("\nImport Summary:"))
        self.stdout.write(f'  Created: {stats["created"]}')
        self.stdout.write(f'  Updated: {stats["updated"]}')
        self.stdout.write(f'  Skipped: {stats["skipped"]}')
        if stats["errors"] > 0:
            self.stdout.write(self.style.ERROR(f'  Errors: {stats["errors"]}'))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No changes made"))
        elif rolled_back:
            self.stdout.write(
                self.style.ERROR(
                    "\n✗ Import ROLLED BACK because of the errors above. "
                    "Nothing was changed; fix the input or pass --allow-partial."
                )
            )
            raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ Import completed"))

    # The full natural key of a rule; a subset (as used before: lemma +
    # word_types + language) mistakes sibling rules that differ in type,
    # pluralization or pattern for "the same rule".
    RULE_NATURAL_KEY = (
        "language",
        "lemma",
        "word_types",
        "type",
        "pluralization",
        "pattern",
    )

    def _import_rule(self, item, pk_mapping, update_existing, replace):
        """Import a Rule object"""
        fields = item["fields"]

        query = {}
        for key in self.RULE_NATURAL_KEY:
            value = fields.get(key)
            if value is None:
                query[f"{key}__isnull"] = True
            else:
                query[key] = value
        existing = Rule.objects.filter(**query).first()

        if existing:
            if update_existing:
                model_fields = {f.name: f for f in existing._meta.get_fields()}
                for key, value in fields.items():
                    field = model_fields.get(key)
                    if key in ("createdby", "ownedby", "id") or field is None:
                        continue
                    if getattr(field, "many_to_many", False):
                        continue
                    if field.is_relation:
                        setattr(existing, f"{key}_id", value)
                    else:
                        setattr(existing, key, value)
                existing.save()
                return {"status": "updated", "new_pk": existing.pk}
            elif replace:
                # Explicitly requested destructive replace: cascades to the
                # rule's children and detaches its own children rules.
                existing.delete()
            else:
                # Fail safe: never silently destroy an existing rule. The
                # operator picks --update-existing or --replace deliberately.
                return {"status": "skipped", "existing_pk": existing.pk}

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None  # Force new object

        # Remap self-referential FKs; refuse to keep a source-side pk that
        # was never remapped (it would point at an arbitrary local rule).
        for self_ref in ("parent", "rule_translation_source"):
            value = fields.get(self_ref)
            if value is None:
                continue
            mapped = pk_mapping.get(f"{RULE}:{value}")
            if mapped is not None:
                setattr(obj, f"{self_ref}_id", mapped)
            else:
                return {
                    "status": "error",
                    "message": (
                        f"rule references {self_ref}={value} which is not part "
                        "of this import; export it too (export_rule includes "
                        "parents automatically) or import it first"
                    ),
                }

        validate_foreign_keys_exist(obj)
        obj.save()

        return {"status": "created", "new_pk": obj.pk}

    def _import_category(self, item, create_deps):
        """Import a Category object"""
        fields = item["fields"]

        # Check if exists by name
        existing = Category.objects.filter(name=fields["name"]).first()

        if existing:
            return {"status": "skipped", "existing_pk": existing.pk}

        if not create_deps:
            return {
                "status": "error",
                "message": f'Category "{fields["name"]}" not found. Use --create-dependencies',
            }

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None
        obj.save()

        return {"status": "created", "new_pk": obj.pk}

    def _import_dimension(self, item, pk_mapping, create_deps):
        """Import a DiversityDimension object"""
        fields = item["fields"]

        # Check if exists
        existing = DiversityDimension.objects.filter(name=fields["name"]).first()

        if existing:
            return {"status": "skipped", "existing_pk": existing.pk}

        if not create_deps:
            return {
                "status": "error",
                "message": f'Dimension "{fields["name"]}" not found. Use --create-dependencies',
            }

        # Resolve category FK; an unmapped value is the source installation's
        # pk and must not be attached to whatever local category owns it.
        cat_pk = fields.get("category")
        if cat_pk:
            mapped_key = f"{CATEGORY}:{cat_pk}"
            if mapped_key in pk_mapping:
                fields["category"] = pk_mapping[mapped_key]
            else:
                return {
                    "status": "error",
                    "message": (
                        f'dimension "{fields.get("name")}" references '
                        f"category={cat_pk} which is not part of this import; "
                        "use export_rule --full to include categories"
                    ),
                }

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None
        obj.save()

        return {"status": "created", "new_pk": obj.pk}

    def _import_source(self, item):
        """Import a Source object"""
        fields = item["fields"]

        # Check if exists by name
        existing = Source.objects.filter(name=fields["name"]).first()

        if existing:
            return {"status": "skipped", "existing_pk": existing.pk}

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None
        validate_foreign_keys_exist(obj)
        obj.save()

        return {"status": "created", "new_pk": obj.pk}

    # FK field -> fixture label of the referenced model. Deriving the label
    # from the field name ("diversity_dimension" -> "rules.diversity_dimension")
    # silently missed the mapping for every model whose class name is not the
    # snake_case field name, so dimension links landed on source-side pks.
    GENERIC_FK_TARGETS = {
        "rule": RULE,
        "parent": RULE,
        "rule_translation_source": RULE,
        "diversity_dimension": DIV_DIM,
        "category": CATEGORY,
        "source": SOURCE,
    }

    # Natural keys used to keep re-imports of child records idempotent.
    GENERIC_UNIQUE_FIELDS = {
        ALTERNATIVE: ("rule", "lemma"),
        TRAINING_SENTENCE: ("rule", "text"),
        FALSE_POSITIVE: ("rule", "false_positive"),
        RULE_DIV_DIM: ("rule", "diversity_dimension"),
    }

    def _import_generic(self, item, pk_mapping):
        """Generic import for related objects"""
        fields = item["fields"]
        model_label = item["model"]

        # Remap FKs using pk_mapping; a child whose rule was not imported in
        # this run must not be attached to whatever local rule carries the
        # source pk.
        for key, target_model in self.GENERIC_FK_TARGETS.items():
            value = fields.get(key)
            if not value:
                continue
            mapped_key = f"{target_model}:{value}"
            if mapped_key in pk_mapping:
                fields[key] = pk_mapping[mapped_key]
            elif key == "rule":
                return {
                    "status": "error",
                    "message": (
                        f"{model_label} references rule={value} which was not "
                        "imported in this run; import the rule first"
                    ),
                }
            else:
                return {
                    "status": "error",
                    "message": (
                        f"{model_label} references {key}={value} which is not "
                        "part of this import; use export_rule --full or import "
                        "the dependency first"
                    ),
                }

        # Idempotence: a re-import must not duplicate children.
        from django.apps import apps

        app_label, model_class_name = model_label.split(".")
        model_class = apps.get_model(app_label, model_class_name)
        unique_fields = self.GENERIC_UNIQUE_FIELDS.get(model_label)
        if unique_fields and all(f in fields for f in unique_fields):
            query = {}
            for f in unique_fields:
                value = fields[f]
                if value is None:
                    query[f"{f}__isnull"] = True
                else:
                    query[f] = value
            existing = model_class.objects.filter(**query).first()
            if existing is not None:
                return {"status": "skipped", "existing_pk": existing.pk}

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None
        obj.save()

        return {"status": "created", "new_pk": obj.pk}
