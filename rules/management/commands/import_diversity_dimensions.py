from django.core.management.base import BaseCommand
from rules.models import DiversityDimension, Category
import json


class Command(BaseCommand):
    help = "Imports and updates the diversity dimensions"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)

    def handle(self, *args, **options):
        diversity_dimensions_file = open(options["file"])
        diversity_dimensions = json.load(diversity_dimensions_file)

        for name in diversity_dimensions:
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

            diversity_dimension.save()

            self.stdout.write(self.style.SUCCESS(message))

            if data["proficiency_level"] != "openly_discriminating":
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

                child.save()

                self.stdout.write(self.style.SUCCESS(message))
