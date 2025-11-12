"""
Auto-generate JSON Schema from Django models.
This keeps the schema in sync with actual model definitions.
"""

from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models
import json
from datetime import datetime

from rules.model_constants import (
    EXPORT_MODELS_BASE,
    EXPORT_MODELS_MAIN,
    EXPORT_MODELS_LINGUISTIC,
    EXPORT_MODELS_EVALUATIONS,
)


class Command(BaseCommand):
    help = "Generate JSON Schema from Django models to keep it in sync with database structure"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="schemas/rules_export_schema.json",
            help="Output schema file (default: schemas/rules_export_schema.json)",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation (default: 2)",
        )

    def _get_field_type(self, field):
        """Map Django field types to JSON Schema types."""
        # Handle foreign keys and relations
        if isinstance(field, models.ForeignKey):
            return {"type": ["integer", "null"]}

        if isinstance(field, models.ManyToManyField):
            return {"type": "array", "items": {"type": "integer"}}

        # Basic type mappings
        type_mapping = {
            models.CharField: {"type": "string"},
            models.TextField: {"type": "string"},
            models.IntegerField: {"type": "integer"},
            models.BigIntegerField: {"type": "integer"},
            models.PositiveIntegerField: {"type": "integer", "minimum": 0},
            models.PositiveSmallIntegerField: {"type": "integer", "minimum": 0},
            models.SmallIntegerField: {"type": "integer"},
            models.FloatField: {"type": "number"},
            models.DecimalField: {"type": "number"},
            models.BooleanField: {"type": "boolean"},
            models.DateField: {"type": "string", "format": "date"},
            models.DateTimeField: {"type": "string", "format": "date-time"},
            models.TimeField: {"type": "string", "format": "time"},
            models.JSONField: {"type": ["object", "array", "string", "null"]},
            models.EmailField: {"type": "string", "format": "email"},
            models.URLField: {"type": "string", "format": "uri"},
            models.UUIDField: {"type": "string", "format": "uuid"},
        }

        for field_class, schema_type in type_mapping.items():
            if isinstance(field, field_class):
                return schema_type.copy()

        # Default to string for unknown types
        return {"type": "string"}

    def _generate_model_schema(self, model):
        """Generate schema definition for a single model."""
        fields_schema = {"type": "object", "properties": {}, "required": []}

        for field in model._meta.get_fields():
            # Skip reverse relations
            if field.auto_created and not field.concrete:
                continue

            field_name = field.name

            # Skip primary key (handled separately in fixture format)
            if field.primary_key:
                continue

            # Get field schema
            field_schema = self._get_field_type(field)

            # Add description from help_text
            if hasattr(field, "help_text") and field.help_text:
                field_schema["description"] = str(field.help_text)

            # Handle nullable fields
            if hasattr(field, "null") and field.null:
                current_type = field_schema.get("type")
                if current_type and current_type != "null":
                    # If type is already a list (e.g., ["integer", "null"]), don't modify
                    if isinstance(current_type, str):
                        field_schema["type"] = [current_type, "null"]

            # Handle max_length
            if hasattr(field, "max_length") and field.max_length:
                field_schema["maxLength"] = field.max_length

            # Handle choices
            if hasattr(field, "choices") and field.choices:
                field_schema["enum"] = [choice[0] for choice in field.choices]

            fields_schema["properties"][field_name] = field_schema

            # Mark required fields (not blank, not null, and not auto-generated)
            if hasattr(field, "blank"):
                # Skip commonly auto-generated fields
                if field_name not in [
                    "created_at",
                    "updated_at",
                    "createdby",
                    "ownedby",
                ]:
                    if not field.blank and not getattr(field, "null", False):
                        fields_schema["required"].append(field_name)

        return fields_schema

    def handle(self, *args, **options):
        output_file = options["output"]
        indent = options["indent"] if options["indent"] > 0 else None

        self.stdout.write(self.style.NOTICE("Generating JSON Schema from models..."))

        # Collect all models
        all_model_paths = [
            *EXPORT_MODELS_BASE,
            *EXPORT_MODELS_MAIN,
            *EXPORT_MODELS_LINGUISTIC,
            *EXPORT_MODELS_EVALUATIONS,
        ]

        # Build definitions
        definitions = {
            "FixtureObject": {
                "type": "object",
                "required": ["model", "pk", "fields"],
                "properties": {
                    "model": {
                        "type": "string",
                        "description": "Django model identifier in format 'app.model'",
                        "enum": [],
                    },
                    "pk": {
                        "type": "integer",
                        "description": "Primary key of the object",
                        "minimum": 1,
                    },
                    "fields": {
                        "type": "object",
                        "description": "Model fields and their values",
                    },
                },
                "allOf": [],
            }
        }

        # Generate schema for each model
        for model_path in all_model_paths:
            app_label, model_name = model_path.split(".")
            model = apps.get_model(app_label, model_name)

            # Add to model enum
            fixture_label = f"{app_label}.{model._meta.model_name}"
            definitions["FixtureObject"]["properties"]["model"]["enum"].append(
                fixture_label
            )

            # Generate field schema
            model_schema = self._generate_model_schema(model)
            definition_name = f"{model.__name__}Fields"
            definitions[definition_name] = model_schema

            # Add conditional schema
            definitions["FixtureObject"]["allOf"].append(
                {
                    "if": {"properties": {"model": {"const": fixture_label}}},
                    "then": {
                        "properties": {
                            "fields": {"$ref": f"#/definitions/{definition_name}"}
                        }
                    },
                }
            )

            self.stdout.write(f"  ✓ Generated schema for {fixture_label}")

        # Build complete schema
        schema = {
            "$schema": "https://json-schema.org/draft-07/schema#",
            "$id": "https://witty-works.com/schemas/rules-export-v1.json",
            "title": "Witty Rules Export Format",
            "description": f"Auto-generated from Django models on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "type": "array",
            "items": {"$ref": "#/definitions/FixtureObject"},
            "definitions": definitions,
        }

        # Write schema
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=indent, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f"\n✓ Generated schema: {output_file}"))
        self.stdout.write(f"  Models: {len(all_model_paths)}")
        self.stdout.write(
            f"  Total definitions: {len(definitions) - 1}"
        )  # -1 for FixtureObject

        # Recommendations
        self.stdout.write("\nRecommended next steps:")
        self.stdout.write("  1. Review the generated schema")
        self.stdout.write(
            f"  2. Validate exports: python validate_export.py data/rules_en.json"
        )
        self.stdout.write("  3. Commit updated schema to version control")
