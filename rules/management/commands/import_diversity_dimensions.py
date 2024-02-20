from django.core.management.base import BaseCommand
from rules.models import DiversityDimension, Category, LanguageEnum
import json


class Command(BaseCommand):
    help = "Imports and updates the diversity dimensions"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)

    def update_language_properties(self, diversity_dimension, data):
        external_name = []
        for language in LanguageEnum:
            setattr(
                diversity_dimension,
                f"has_{language}_rules",
                language in data[f"has_rules"],
            )

            if "translations" in data and language in data["translations"]:
                setattr(
                    diversity_dimension,
                    f"url_{language}",
                    data["translations"][language]["canonical_url"],
                )

                external_name.append(data["translations"][language]["hs_name"])

        diversity_dimension.external_name = (" / ").join(external_name)

    def handle(self, *args, **options):
        diversity_dimensions_file = open(options["file"])
        diversity_dimensions = json.load(diversity_dimensions_file)

        for name in diversity_dimensions:
            self.stdout.write(self.style.WARNING(f"Processing {name}"))

            data = diversity_dimensions[name]

            if "translations" not in data or "proficiency_level" not in data:
                continue

            try:
                diversity_dimension = DiversityDimension.objects.get(name=name)
                message = f"Successfully updated diversity dimension '{name}'"
            except DiversityDimension.DoesNotExist:
                diversity_dimension = DiversityDimension()
                diversity_dimension.name = name
                message = f"Successfully created diversity dimension '{name}'"

            try:
                category = Category.objects.get(name=data["category"])
            except Category.DoesNotExist:
                category = Category()
                category.name = data["category"]
                category.save()

            diversity_dimension.category = category
            diversity_dimension.parent_name = name
            diversity_dimension.proficiency_level = (
                data["proficiency_level"].strip().lower()
            )

            self.update_language_properties(diversity_dimension, data)

            diversity_dimension.save()

            self.stdout.write(self.style.SUCCESS(message))

            if data["proficiency_level"] not in ["openly_discriminating", "inclusive"]:
                advanced_name = f"{name}_advanced"

                try:
                    child = DiversityDimension.objects.get(name=advanced_name)
                    message = (
                        f"Successfully updated diversity dimension '{advanced_name}'"
                    )
                except DiversityDimension.DoesNotExist:
                    child = DiversityDimension()
                    child.name = advanced_name
                    message = (
                        f"Successfully created diversity dimension '{advanced_name}'"
                    )

                child.category = category
                child.parent_name = name
                child.proficiency_level = data["proficiency_level"].strip().lower()
                self.update_language_properties(child, data)

                child.save()

                self.stdout.write(self.style.SUCCESS(message))
