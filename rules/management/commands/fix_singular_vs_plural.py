from django.core.management.base import BaseCommand
from rules.models import Alternative
from django.db import connection


class Command(BaseCommand):
    help = "Remove redundant plural alternatives"

    def handle(self, *args, **options):
        query = """select ras.id, rap.id, rap.rule_id
            from rules_alternative ras
            inner join rules_alternative rap on ras.rule_id = rap.rule_id
            where ras.pluralization = 'singular_only'
                and rap.pluralization = 'plural_only'
                and (
                    (ras.lemma || 's') = rap.lemma
                        or (ras.lemma || 'n') = rap.lemma
                        or (ras.lemma || 'en') = rap.lemma
                        or ras.lemma = replace(rap.lemma, 'people', 'person')
                )"""

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

            for row in rows:
                print(row[2])

                singular_alternative = Alternative.objects.get(id=row[0])
                print(singular_alternative)
                singular_alternative.pluralization = "default"
                singular_alternative.save()

                plural_alternative = Alternative.objects.get(id=row[1])
                print(plural_alternative)

                plural_alternative.delete()
