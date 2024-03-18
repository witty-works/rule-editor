from django.core.management.base import BaseCommand
from rules.admin import apply_rule
from rules.models import Rule, TrainingSentence
import sqlite3


class Command(BaseCommand):
    help = "Copy training sentences from an external SQLite DB into the local SQLite DB"

    def add_arguments(self, parser):
        parser.add_argument("--sqlitedb", type=str)

    def handle(self, *args, **options):
        con = sqlite3.connect(options["sqlitedb"])

        rules = Rule.objects.filter(language="en")
        for rule in rules:
            generated_sentences = []

            try:
                training_sentences = TrainingSentence.objects.filter(rule=rule)
                if len(training_sentences) < 2:
                    generated_sentences = []
                    query = f"SELECT text FROM rules_trainingsentence WHERE rule_id = ? AND comment = ? AND text NOT LIKE ?"
                    for generated_sentence in con.execute(
                        query, [rule.id, "auto generated", "I'm sorry%"]
                    ):
                        generated_sentences.append(generated_sentence[0])

                    for training_sentence in training_sentences:
                        if training_sentence.text in generated_sentences:
                            generated_sentences.remove(training_sentence.text)

                    for generated_sentence in generated_sentences:
                        sentence = TrainingSentence()
                        sentence.text = generated_sentence
                        sentence.comment = "auto generated"
                        sentence.rule = rule
                        sentence.save()

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Added sentence to rule '{rule}':\n"
                                + generated_sentence
                                + "\n\n"
                            )
                        )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to handle rule sentences for rule '{rule}'. Error: {e}"
                    )
                )
