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
from rules.export_utils import load_json


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
            help="Skip rules that already exist (by lemma + word_types + language)",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing rules with imported data",
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
        owner = options["owner"]
        dry_run = options["dry_run"]
        create_deps = options["create_dependencies"]

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

        # Import each model
        for model_name in import_order:
            if model_name not in by_model:
                continue

            items = by_model[model_name]
            self.stdout.write(f"\n{model_name}: {len(items)} object(s)")

            for item in items:
                pk = item.get("pk")
                fields = item.get("fields", {})

                # Assign owner if requested (for all models with user references)
                if owner_user and model_name in MODELS_WITH_USER_REFS:
                    # Assign createdby if field exists
                    if "createdby" in fields:
                        fields["createdby"] = owner_user.id
                    # Assign ownedby if field exists (only Rule has this)
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
                                item, pk_mapping, skip_existing, update_existing
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
                            # Generic import for related objects
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
                            pk_mapping[f"{model_name}:{pk}"] = result["existing_pk"]
                        elif result["status"] == "error":
                            stats["errors"] += 1
                            self.stdout.write(
                                self.style.ERROR(f'  ✗ Error: {result["message"]}')
                            )

                except Exception as e:
                    stats["errors"] += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ Error importing {model_name} pk={pk}: {e}"
                        )
                    )

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
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ Import completed"))

    def _import_rule(self, item, pk_mapping, skip_existing, update_existing):
        """Import a Rule object"""
        fields = item["fields"]

        # Check if rule exists
        existing = Rule.objects.filter(
            lemma=fields["lemma"],
            word_types=fields.get("word_types", ""),
            language=fields["language"],
        ).first()

        if existing:
            if skip_existing:
                return {"status": "skipped", "existing_pk": existing.pk}
            elif update_existing:
                # Update existing
                for key, value in fields.items():
                    if key not in ["createdby", "ownedby", "id"]:
                        setattr(existing, key, value)
                existing.save()
                return {"status": "updated", "new_pk": existing.pk}
            else:
                # Replace
                existing.delete()

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None  # Force new object
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

        # Resolve category FK
        cat_pk = fields.get("category")
        if cat_pk:
            mapped_key = f"{CATEGORY}:{cat_pk}"
            if mapped_key in pk_mapping:
                fields["category"] = pk_mapping[mapped_key]

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
        obj.save()

        return {"status": "created", "new_pk": obj.pk}

    def _import_generic(self, item, pk_mapping):
        """Generic import for related objects"""
        fields = item["fields"]

        # Remap FKs using pk_mapping
        for key, value in fields.items():
            if key.endswith("_id") or key in [
                "rule",
                "diversity_dimension",
                "source",
                "parent",
            ]:
                if value:
                    # Try to find mapping
                    model_name = (
                        item["model"].rsplit(".", 1)[0] + "." + key.replace("_id", "")
                    )
                    mapped_key = f"{model_name}:{value}"
                    if mapped_key in pk_mapping:
                        fields[key] = pk_mapping[mapped_key]

        # Create new
        obj_data = json.dumps([item])
        objects = list(serializers.deserialize("json", obj_data))
        obj = objects[0].object
        obj.pk = None
        obj.save()

        return {"status": "created", "new_pk": obj.pk}
