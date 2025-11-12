"""
Assign ownership of rules to a specific user.
Useful after importing rules without user attribution.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from rules.models import Rule


class Command(BaseCommand):
    help = """
    Assign ownership of rules to a specific user.
    Useful after importing rules from external sources.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--username", type=str, required=True, help="Username to assign rules to"
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Assign all rules (including those with existing owners)",
        )
        parser.add_argument(
            "--unowned-only",
            action="store_true",
            default=True,
            help="Only assign unowned rules (default behavior)",
        )
        parser.add_argument(
            "--language",
            type=str,
            choices=["en", "de", "fr"],
            help="Only assign rules for specific language",
        )
        parser.add_argument(
            "--dimension",
            type=str,
            help="Only assign rules in specific diversity dimension",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without making changes",
        )

    def handle(self, *args, **options):
        username = options["username"]
        assign_all = options["all"]
        unowned_only = options["unowned_only"] and not assign_all
        language = options.get("language")
        dimension = options.get("dimension")
        dry_run = options["dry_run"]

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User "{username}" not found'))
            return

        # Build query
        rules = Rule.objects.all()

        if unowned_only:
            rules = rules.filter(ownedby__isnull=True)

        if language:
            rules = rules.filter(language=language)

        if dimension:
            rules = rules.filter(diversity_dimensions__name__icontains=dimension)

        count = rules.count()

        if count == 0:
            self.stdout.write("No rules found matching criteria")
            return

        self.stdout.write(f"Found {count} rule(s) to assign to {username}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )
            for rule in rules[:10]:  # Show first 10
                self.stdout.write(f"  Would assign: {rule.lemma} ({rule.language})")
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
        else:
            # Assign ownership
            updated = rules.update(ownedby=user, createdby=user)

            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Assigned {updated} rule(s) to {username}")
            )
