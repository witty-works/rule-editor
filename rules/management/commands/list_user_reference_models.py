"""
List all models with user references (createdby/ownedby fields).
Useful for debugging and verification.
"""

from django.core.management.base import BaseCommand
from django.apps import apps


class Command(BaseCommand):
    help = "List all models with user reference fields (createdby/ownedby)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\nModels with User References:"))
        self.stdout.write("=" * 70)

        models_found = []

        # Get all models from rules app
        for model in apps.get_app_config("rules").get_models():
            fields = [f.name for f in model._meta.get_fields()]

            has_createdby = "createdby" in fields
            has_ownedby = "ownedby" in fields

            if has_createdby or has_ownedby:
                models_found.append(
                    {
                        "name": model.__name__,
                        "app_label": model._meta.app_label,
                        "model_name": model._meta.model_name,
                        "has_createdby": has_createdby,
                        "has_ownedby": has_ownedby,
                    }
                )

        # Sort by name
        models_found.sort(key=lambda x: x["name"])

        # Print table
        self.stdout.write(
            f"\n{'Model':<30} {'createdby':<12} {'ownedby':<12} {'Full Name'}"
        )
        self.stdout.write("-" * 70)

        for model in models_found:
            createdby = "✅" if model["has_createdby"] else "❌"
            ownedby = "✅" if model["has_ownedby"] else "❌"
            full_name = f"{model['app_label']}.{model['model_name']}"

            self.stdout.write(
                f"{model['name']:<30} {createdby:<12} {ownedby:<12} {full_name}"
            )

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"Total models with user references: {len(models_found)}")

        createdby_count = sum(1 for m in models_found if m["has_createdby"])
        ownedby_count = sum(1 for m in models_found if m["has_ownedby"])

        self.stdout.write(f"  - With 'createdby': {createdby_count}")
        self.stdout.write(f"  - With 'ownedby': {ownedby_count}")

        # Generate code for import commands
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("Code for import commands:")
        self.stdout.write("-" * 70)
        self.stdout.write("models_with_user_refs = {")
        for model in models_found:
            full_name = f"{model['app_label']}.{model['model_name']}"
            self.stdout.write(f"    '{full_name}',")
        self.stdout.write("}")
        self.stdout.write("")
