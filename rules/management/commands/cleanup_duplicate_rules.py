"""
Clean up duplicate rules based on unique constraints.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from rules.models import Rule


class Command(BaseCommand):
    help = """
    Find and optionally remove duplicate rules.
    Duplicates are identified by: lemma + word_types + language
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--remove",
            action="store_true",
            help="Remove duplicates (keeps newest by updated_at)",
        )
        parser.add_argument(
            "--keep",
            type=str,
            default="newest",
            choices=["newest", "oldest", "first", "last"],
            help="Which duplicate to keep (default: newest)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Show duplicates without removing"
        )

    def handle(self, *args, **options):
        remove = options["remove"]
        keep = options["keep"]
        dry_run = options["dry_run"]

        # Find duplicates
        self.stdout.write("Searching for duplicate rules...")

        duplicates = (
            Rule.objects.values("lemma", "word_types", "language")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        if not duplicates:
            self.stdout.write(self.style.SUCCESS("No duplicates found"))
            return

        self.stdout.write(f"Found {len(duplicates)} duplicate groups")

        total_to_remove = 0

        for dup in duplicates:
            lemma = dup["lemma"]
            word_types = dup["word_types"]
            language = dup["language"]
            count = dup["count"]

            self.stdout.write(
                f"\nDuplicate: {lemma} / {word_types} ({language}) - {count} instances"
            )

            # Get all instances
            instances = Rule.objects.filter(
                lemma=lemma, word_types=word_types, language=language
            )

            # Determine which to keep
            if keep == "newest":
                keeper = instances.order_by("-updated_at").first()
            elif keep == "oldest":
                keeper = instances.order_by("updated_at").first()
            elif keep == "first":
                keeper = instances.order_by("id").first()
            else:  # last
                keeper = instances.order_by("-id").first()

            to_remove = instances.exclude(id=keeper.id)

            self.stdout.write(f"  Keep: ID={keeper.id} (updated: {keeper.updated_at})")
            self.stdout.write(f"  Remove: {to_remove.count()} duplicate(s)")

            for rule in to_remove:
                self.stdout.write(f"    - ID={rule.id} (updated: {rule.updated_at})")
                total_to_remove += 1

            if remove and not dry_run:
                deleted_count = to_remove.delete()[0]
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Removed {deleted_count} duplicate(s)")
                )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(f"\nTotal duplicates to remove: {total_to_remove}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN - No changes made. Use --remove to delete duplicates"
                )
            )
        elif not remove:
            self.stdout.write(self.style.NOTICE("Use --remove to delete duplicates"))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Removed {total_to_remove} duplicate rule(s)")
            )
