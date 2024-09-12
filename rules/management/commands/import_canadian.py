from django.core.management.base import BaseCommand
from rules.models import (
    Rule,
    Alternative,
    TrainingSentence,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
)
import csv


class Command(BaseCommand):
    help = "Imports canadian rules"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)
        parser.add_argument("--language", type=str)
        parser.add_argument("--limit", type=int, default=False)

    def handle(self, *args, **options):
        language = options["language"]
        limit = options["limit"]

        data = DiversityDimension.objects.filter()
        diversity_dimensions = {}
        for diversity_dimension in data:
            diversity_dimensions[diversity_dimension.name] = diversity_dimension

        diversity_dimension_map = {
            "(nom)": ["n", diversity_dimensions["titles"]],
            "(pronom)": ["pron", diversity_dimensions["function"]],
            "adjectif": ["a", diversity_dimensions["function"]],
            "(verbe)": ["v", diversity_dimensions["function"]],
            "(déterminant)": ["pron", diversity_dimensions["function"]],
        }

        source = Source.objects.get(id=16)

        rules = {}
        with open(options["file"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if limit is not False and len(rules) == limit:
                    break

                comment = row["lemma"].strip()
                if len(comment):
                    word_types = None
                    for diversity_dimension_mapping in diversity_dimension_map:
                        if diversity_dimension_mapping in comment:
                            word_types = diversity_dimension_map[
                                diversity_dimension_mapping
                            ][0]
                            diversity_dimension = diversity_dimension_map[
                                diversity_dimension_mapping
                            ][1]

                    # self.stdout.write(
                    #    self.style.NOTICE(
                    #        f"Processing lemma '{comment}' / '{word_types}'"
                    #    )
                    # )

                    continue

                lemma = row["rule lemma"].strip()
                if word_types is None:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Skipping lemma '{lemma}' due to missing word_type"
                        )
                    )

                    continue

                try:
                    rule = Rule.objects.get(
                        lemma=lemma, word_types=word_types, language=language
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"Skipping lemma '{lemma}' as the rule already exists as {rule} / {rule.id}"
                        )
                    )
                    continue
                except Rule.DoesNotExist:
                    pass

                key = lemma + "|" + word_types
                if key not in rules:
                    rules[key] = {
                        "word_types": word_types,
                        "language": language,
                        "lemma": lemma,
                        "text_id": lemma,
                        "alternatives": [],
                        "sentences": [],
                        "comment": comment,
                        "diversity_dimension": diversity_dimension,
                    }

                rules[key]["sentences"].append(row["rule text"].strip())

                for i in range(1, 8):
                    alternative = row["alternative" + str(i)].strip()
                    if len(alternative):
                        rules[key]["alternatives"].append(alternative)

        for key in rules:
            rule_data = rules[key]

            rule = Rule()
            rule.lemma = rule_data["lemma"]
            rule.text_id = rule_data["text_id"]
            rule.word_types = rule_data["word_types"]
            rule.language = rule_data["language"]
            rule.comment = rule_data["comment"]
            rule.is_marked_for_review = True
            rule.source = source
            rule.is_active = False
            rule.save()

            rule_diversity_dimension = RuleDiversityDimension()
            rule_diversity_dimension.rule = rule
            rule_diversity_dimension.order = 0
            rule_diversity_dimension.diversity_dimension = rule_data["diversity_dimension"]
            rule_diversity_dimension.save()

            alternative_count = 0
            for alternative_lemma in rule_data["alternatives"]:
                alternative = Alternative()
                alternative.rule = rule
                alternative.language = rule.language
                alternative.lemma = alternative_lemma
                alternative.is_collective_noun = "~" in alternative_lemma
                alternative.source = source
                alternative.order = alternative_count
                alternative.save()
                alternative_count += 1

            for sentence in rule_data["sentences"]:
                training_sentence = TrainingSentence()
                training_sentence.rule = rule
                training_sentence.text = sentence
                training_sentence.is_false_positive = False
                training_sentence.is_training_data = False
                training_sentence.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully created rule '{rule.lemma}' / '{rule.word_types}'"
                )
            )
