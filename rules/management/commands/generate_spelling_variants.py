from breame.spelling import (
    american_spelling_exists,
    british_spelling_exists,
    get_american_spelling,
    get_british_spelling,
)
from django.core.management.base import BaseCommand

from rules.models import Lemmatization, Rule


class Command(BaseCommand):
    help = (
        "Create rules_lemmatization entries pinning en-GB/en-US spelling "
        "variants of every English rule word to the spelling the rule uses "
        "(coloured -> colored), so rules match both variants regardless of "
        "which spelling the model's lemmatizer knows. Idempotent; dry-run "
        "unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        apply = options["apply"]
        if not apply:
            self.stdout.write(self.style.WARNING("Dry run; pass --apply to write"))

        tokens = set()
        for lemma_json in Rule.objects.filter(
            language="en", is_active=True
        ).values_list("lemma_json", flat=True):
            for token in lemma_json or []:
                token = token.lower()
                if token.isalpha():
                    tokens.add(token)

        created = existing = conflicts = 0
        for token in sorted(tokens):
            variants = set()
            if british_spelling_exists(token):
                variants.add(get_american_spelling(token))
            if american_spelling_exists(token):
                variants.add(get_british_spelling(token))
            variants.discard(token)

            for variant in sorted(variants):
                if variant in tokens:
                    # Both spellings are rule words in their own right (grey /
                    # gray): a pin would rewrite one rule's key into the
                    # other's and break its matching. Those rules already
                    # cover both variants.
                    continue

                pin = Lemmatization.objects.filter(
                    language="en", text=variant, word_type=""
                ).first()
                if pin:
                    if pin.lemma != token:
                        conflicts += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"! {variant!r} already pinned to {pin.lemma!r}, "
                                f"wanted {token!r}; leaving as is"
                            )
                        )
                    else:
                        existing += 1
                    continue

                created += 1
                self.stdout.write(f"+ ({'en'}) {variant!r} -> {token!r}")
                if apply:
                    Lemmatization.objects.create(
                        language="en",
                        text=variant,
                        lemma=token,
                        word_type="",
                        is_plural=False,
                        comment="en-GB/en-US spelling variant (generate_spelling_variants)",
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"{created} new, {existing} already present, {conflicts} conflicts "
                f"({len(tokens)} distinct English rule words)"
            )
        )
