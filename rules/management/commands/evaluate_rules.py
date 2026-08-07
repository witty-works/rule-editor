import json
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand, CommandError

from rules.evaluation import build_rule_payload, evaluate_sentence, fetch_api_version
from rules.models import (
    EvaluationRun,
    Rule,
    RuleEvaluation,
    TrainingSentence,
    TrainingSentenceEvaluation,
)
from django.conf import settings


class Command(BaseCommand):
    help = (
        "Evaluate every rule's training sentences against the NLP API and store "
        "the per-sentence pass/fail state stamped with the API's git revision "
        "and spaCy/model versions. Reports the diff against the stored "
        "has_failing_training_sentence flags: was-failing/now-passing, "
        "was-passing/now-failing, still-failing."
    )

    def add_arguments(self, parser):
        parser.add_argument("--lang", type=str)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--rule-ids", type=str, help="Comma separated rule ids")
        parser.add_argument("--include-inactive", action="store_true")
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--json-output", type=str, help="Write full report JSON")
        parser.add_argument(
            "--update-flags",
            action="store_true",
            help="Also write the new state back to has_failing_training_sentence",
        )
        parser.add_argument("--comment", type=str, default="")

    def handle(self, *args, **options):
        try:
            version = fetch_api_version()
        except Exception as exception:
            raise CommandError(
                f"NLP API at {settings.NLP_API} did not answer /version: {exception}. "
                "Evaluation state must be stamped; refusing to run unversioned."
            )

        if not version.get("git_revision"):
            self.stdout.write(
                self.style.WARNING(
                    "API reports no git revision (image built without "
                    "GIT_REVISION); stamping app/spaCy versions only"
                )
            )

        run = EvaluationRun.objects.create(
            nlp_api_url=settings.NLP_API,
            api_app_version=version.get("app_version", ""),
            api_git_revision=version.get("git_revision", ""),
            spacy_version=version.get("spacy_version", ""),
            model_versions=version.get("models", {}),
            comment=options["comment"],
        )
        self.stdout.write(self.style.SUCCESS(f"Started {run}"))

        rules = Rule.objects.all()
        if not options["include_inactive"]:
            rules = rules.filter(is_active=True)
        if options["lang"]:
            rules = rules.filter(language=options["lang"])
        if options["rule_ids"]:
            rules = rules.filter(
                pk__in=[int(pk) for pk in options["rule_ids"].split(",")]
            )
        rules = rules.order_by("pk")
        if options["limit"]:
            rules = rules[: options["limit"]]

        report = {
            "run": run.pk,
            "nlp_api_url": run.nlp_api_url,
            "api_app_version": run.api_app_version,
            "api_git_revision": run.api_git_revision,
            "spacy_version": run.spacy_version,
            "model_versions": run.model_versions,
            "was_failing_now_passing": [],
            "was_passing_now_failing": [],
            "still_failing": [],
            "errors": [],
            "rules_without_sentences": [],
        }

        checked = 0
        for rule in rules.iterator():
            sentences = list(TrainingSentence.objects.filter(rule=rule))
            if not sentences:
                report["rules_without_sentences"].append(rule.pk)
                continue

            payload = build_rule_payload(rule)

            def evaluate(sentence):
                matched, error = evaluate_sentence(payload, sentence.text)
                return sentence, matched, error

            with ThreadPoolExecutor(max_workers=options["workers"]) as executor:
                results = list(executor.map(evaluate, sentences))

            evaluations = []
            failed = errors = 0
            failing_sentences = []
            for sentence, matched, error in results:
                if matched is None:
                    passed = None
                    errors += 1
                    report["errors"].append(
                        {"rule": rule.pk, "sentence": sentence.pk, "error": error}
                    )
                else:
                    passed = matched != sentence.is_false_positive
                    if not passed and not sentence.is_false_positive:
                        failed += 1
                        failing_sentences.append(sentence.text)

                evaluations.append(
                    TrainingSentenceEvaluation(
                        run=run,
                        training_sentence=sentence,
                        rule=rule,
                        matched=matched,
                        passed=passed,
                        is_false_positive=sentence.is_false_positive,
                        error=error,
                    )
                )

            TrainingSentenceEvaluation.objects.bulk_create(evaluations)

            # Rule-level "failing" mirrors what check_rules always meant:
            # a positive sentence that does not trigger the rule. Misbehaving
            # false-positive sentences and API errors are reported but do not
            # decide the flag.
            failing = failed > 0
            RuleEvaluation.objects.create(
                run=run,
                rule=rule,
                failing=failing,
                previous_flag=rule.has_failing_training_sentence,
                sentence_count=len(sentences),
                failed_count=failed,
                error_count=errors,
            )

            entry = {
                "rule": rule.pk,
                "lemma": rule.lemma,
                "language": str(rule.language),
                "word_types": rule.word_types,
                "failing_sentences": failing_sentences,
            }
            if rule.has_failing_training_sentence and not failing:
                report["was_failing_now_passing"].append(entry)
            elif not rule.has_failing_training_sentence and failing:
                report["was_passing_now_failing"].append(entry)
            elif failing:
                report["still_failing"].append(entry)

            if options["update_flags"]:
                Rule.objects.filter(pk=rule.pk).update(
                    has_failing_training_sentence=failing
                )

            checked += 1
            if checked % 100 == 0:
                self.stdout.write(f"... {checked} rules evaluated")

        for key in (
            "was_failing_now_passing",
            "was_passing_now_failing",
            "still_failing",
        ):
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"{key} ({len(report[key])}):")
            )
            for entry in report[key]:
                self.stdout.write(
                    f"  #{entry['rule']} {entry['lemma']} - {entry['word_types']} ({entry['language']})"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Evaluated {checked} rules "
                f"({len(report['rules_without_sentences'])} without sentences, "
                f"{len(report['errors'])} API errors) as {run}"
            )
        )

        if options["json_output"]:
            with open(options["json_output"], "w") as file:
                json.dump(report, file, indent=2, ensure_ascii=False)
            self.stdout.write(f"Report written to {options['json_output']}")
