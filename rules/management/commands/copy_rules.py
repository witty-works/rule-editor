from django.core.management.base import BaseCommand
from rules.models import Rule, RuleDiversityDimension, TrainingSentence, Alternative
import sqlite3


class Command(BaseCommand):
    help = (
        "Copy auto generated rules from an external SQLite DB into the local SQLite DB"
    )

    def add_arguments(self, parser):
        parser.add_argument("--sqlitedb", type=str)

    def handle(self, *args, **options):
        con = sqlite3.connect(options["sqlitedb"])

        # TODO currently we assume that the DiversityDimension table data exactly matches in both databases

        rule_fields = []
        for rule_field in Rule._meta.get_fields():
            if rule_field.many_to_one or rule_field.related_model:
                continue
            rule_fields.append(rule_field.name)

        rule_field_list = '"' + '","'.join(rule_fields) + '"'

        alternative_fields = []
        for alternative_field in Alternative._meta.get_fields():
            if (
                alternative_field.many_to_one
                or alternative_field.related_model
                or alternative_field == "rule_id"
            ):
                continue
            alternative_fields.append(alternative_field.name)

        alternative_field_list = '"' + '","'.join(alternative_fields) + '"'

        training_sentence_fields = []
        for training_sentence_field in TrainingSentence._meta.get_fields():
            if (
                training_sentence_field.many_to_one
                or training_sentence_field.related_model
                or training_sentence_field == "rule_id"
            ):
                continue
            training_sentence_fields.append(training_sentence_field.name)

        training_sentence_field_list = '"' + '","'.join(training_sentence_fields) + '"'

        rule_dd_fields = ["diversity_dimension_id"]
        for rule_dd_field in RuleDiversityDimension._meta.get_fields():
            if (
                rule_dd_field.many_to_one
                or rule_dd_field.related_model
                or rule_dd_field == "rule_id"
            ):
                continue
            rule_dd_fields.append(rule_dd_field.name)

        rule_dd_field_list = '"' + '","'.join(rule_dd_fields) + '"'

        query = f"SELECT {rule_field_list} FROM rules_rule WHERE is_auto_generated = ?"
        for rule_data in con.execute(query, [1]):
            rule_data = dict(zip(rule_fields, rule_data))

            try:
                rule = Rule()
                for rule_field in rule_fields:
                    if rule_field == "id":
                        continue

                    rule.__setattr__(rule_field, rule_data[rule_field])

                rule.save()

                query = f"SELECT {alternative_field_list} FROM rules_alternative WHERE rule_id = ?"
                for alternative_data in con.execute(query, [rule_data["id"]]):
                    alternative_data = dict(zip(alternative_fields, alternative_data))
                    alternative = Alternative()
                    alternative.rule = rule
                    for alternative_field in alternative_fields:
                        if alternative_field == "id":
                            continue

                        alternative.__setattr__(
                            alternative_field, alternative_data[alternative_field]
                        )

                    alternative.save()

                query = f"SELECT {training_sentence_field_list} FROM rules_trainingsentence WHERE rule_id = ?"
                for training_sentence_data in con.execute(query, [rule_data["id"]]):
                    training_sentence_data = dict(
                        zip(training_sentence_fields, training_sentence_data)
                    )
                    training_sentence = TrainingSentence()
                    training_sentence.rule = rule
                    for training_sentence_field in training_sentence_fields:
                        if training_sentence_field == "id":
                            continue

                        training_sentence.__setattr__(
                            training_sentence_field,
                            training_sentence_data[training_sentence_field],
                        )

                    training_sentence.save()

                query = f"SELECT {rule_dd_field_list} FROM rules_rulediversitydimension WHERE rule_id = ?"
                for rule_dd_data in con.execute(query, [rule_data["id"]]):
                    rule_dd_data = dict(zip(rule_dd_fields, rule_dd_data))
                    rule_dd = RuleDiversityDimension()
                    rule_dd.rule = rule
                    for rule_dd_field in rule_dd_fields:
                        if rule_dd_field == "id":
                            continue

                        rule_dd.__setattr__(rule_dd_field, rule_dd_data[rule_dd_field])

                    rule_dd.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        "Successfully handled rule '%s' - '%s' (%s)."
                        % (
                            rule_data["lemma"],
                            rule_data["word_types_json"],
                            rule_data["language"],
                        )
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        "Failed to handled rule '%s' - '%s' (%s).\n Error: %s"
                        % (
                            rule_data["lemma"],
                            rule_data["word_types_json"],
                            rule_data["language"],
                            repr(e),
                        )
                    )
                )
