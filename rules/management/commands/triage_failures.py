import difflib
import json

from django.core.management.base import BaseCommand, CommandError

from rules.evaluation import analyze_text
from rules.models import (
    EvaluationRun,
    Rule,
    RuleEvaluation,
    TrainingSentenceEvaluation,
)

# Content words carry the rule's meaning in any reading (slurs, exaggerations,
# coinages): when the tagger reads them as another POS the durable fix is to
# stop constraining the POS (word_type "", precedent: guru). Function and
# degree words are the opposite: their word type plus false-positive lists are
# deliberate precision controls, so a new reading warrants a sibling rule with
# its own alternatives (precedent: ninja a/n).
CONTENT_WORD_TYPES = {"n", "v", "a"}
FUNCTION_WORD_TYPES = {"adv", "conj", "pron", "num", "card", "article"}

# Dimensions whose terms are problematic in any reading (slurs, insults,
# exaggerations/coinages): the only class where dropping the POS constraint
# is safe. Everything else keeps its word type as a precision control and is
# adjudicated manually (or gets a sibling when a second reading is genuine).
MARKED_DIMENSIONS = {
    "offensive_language",
    "exaggerating",
    "exaggerating_advanced",
    "homophobia",
    "transphobia",
    "antisemitism",
    "antimuslim",
    "racism",
    "racist_source",
    "racist_source_advanced",
    "nazi_language",
    "nazi_language_advanced",
    "xenophobia",
    "ableism",
    "yiddish-pejoratives",
    "yiddish-pejoratives_advanced",
}


class Command(BaseCommand):
    help = (
        "Classify why rules failed an evaluation run: (a) word-type mismatch, "
        "(b) lemma drift, (c) other. Shows the tagger's actual reading "
        "(pos/tag/lemma/morph) next to the rule's declaration and proposes a "
        "correction per the codebase's precedents."
    )

    def add_arguments(self, parser):
        parser.add_argument("--run", type=int, help="Evaluation run id (default: latest)")
        parser.add_argument("--lang", type=str)
        parser.add_argument("--json-output", type=str)
        parser.add_argument(
            "--include-passing-flag-mismatch",
            action="store_true",
            help="Also triage rules whose stored flag already said failing",
        )

    def handle(self, *args, **options):
        if options["run"]:
            run = EvaluationRun.objects.get(pk=options["run"])
        else:
            run = EvaluationRun.objects.order_by("-pk").first()
        if run is None:
            raise CommandError("No evaluation run found; run evaluate_rules first")

        rule_evaluations = RuleEvaluation.objects.filter(
            run=run, failing=True
        ).select_related("rule")
        if options["lang"]:
            rule_evaluations = rule_evaluations.filter(rule__language=options["lang"])

        report = {
            "run": run.pk,
            "api_git_revision": run.api_git_revision,
            "spacy_version": run.spacy_version,
            "model_versions": run.model_versions,
            "classes": {"word_type_mismatch": [], "lemma_drift": [], "other": []},
        }

        for rule_evaluation in rule_evaluations:
            rule = rule_evaluation.rule
            entry = self.triage_rule(run, rule)
            report["classes"][entry["class"]].append(entry)

        for class_name, entries in report["classes"].items():
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"{class_name} ({len(entries)}):")
            )
            for entry in entries:
                action = entry["proposed_action"]["action"]
                self.stdout.write(
                    f"  #{entry['rule']} {entry['lemma']!r} declared={entry['word_types']} "
                    f"({entry['language']}) -> {action}"
                )
                for sentence in entry["sentences"]:
                    token = sentence.get("token")
                    if token:
                        self.stdout.write(
                            f"      token {token['text']!r} lemma={token['lemma']!r} "
                            f"word_type={token['word_type']} pos={token.get('pos')} "
                            f"tag={token.get('tag')} morph={token.get('morph')}"
                        )
                    else:
                        self.stdout.write(
                            f"      no anchor token found in: {sentence['text'][:80]!r}"
                        )

        if options["json_output"]:
            with open(options["json_output"], "w") as file:
                json.dump(report, file, indent=2, ensure_ascii=False)
            self.stdout.write(f"Report written to {options['json_output']}")

    def triage_rule(self, run, rule):
        failing = TrainingSentenceEvaluation.objects.filter(
            run=run, rule=rule, passed=False, is_false_positive=False
        ).select_related("training_sentence")

        word_types_json = rule.word_types_json or []
        first = word_types_json[0] if word_types_json else {}
        declared_type = first.get("word_type", "")

        # One (anchor, declared, lemmatize) triple per rule token: a phrase
        # rule can fail on any of its tokens, not just the first (colored
        # person fails on people, not on colored).
        positions = []
        for index, rule_token in enumerate(rule.lemma_json or []):
            token_types = (
                word_types_json[index] if index < len(word_types_json) else {}
            )
            anchor = rule_token
            if token_types.get("lower_case", True):
                anchor = anchor.lower()
            positions.append(
                (
                    anchor,
                    token_types.get("word_type", ""),
                    token_types.get("lemmatize", True),
                )
            )

        sibling_word_types = list(
            Rule.objects.filter(language=rule.language, lemma=rule.lemma)
            .exclude(pk=rule.pk)
            .values_list("word_types", flat=True)
        )

        sentence_entries = []
        classes = []
        pin = None
        observed_types = []
        for sentence_evaluation in failing:
            text = sentence_evaluation.training_sentence.text
            try:
                auto_word_types, tokens = analyze_text(
                    str(rule.language), text, detailed=True
                )
            except Exception as exception:
                sentence_entries.append({"text": text, "error": str(exception)})
                classes.append("other")
                continue

            # Classify on the first rule token with a problem; a clean first
            # token does not clear a phrase rule whose second token drifted.
            sentence_class = None
            sentence_entry = {"text": text}
            for position, (anchor, declared, lemmatize) in enumerate(positions):
                token, match = self.find_anchor(anchor, tokens)
                if position == 0 or sentence_class is None:
                    sentence_entry["match"] = match
                    if token is not None:
                        sentence_entry["token"] = {
                            "text": token.get("text"),
                            "lemma": token.get("lemma"),
                            "word_type": token.get("word_type"),
                            "pos": token.get("pos"),
                            "tag": token.get("tag"),
                            "morph": token.get("morph"),
                        }

                if token is None:
                    sentence_class = sentence_class or "other"
                    continue

                if match == "fuzzy":
                    # Surface form the pipeline neither reads as the rule key
                    # nor lemmatizes to it (inflection or spelling variant).
                    sentence_class = "lemma_drift"
                    pin = pin or self.build_pin(rule, anchor, token)
                elif declared and token.get("word_type") != declared:
                    sentence_class = "word_type_mismatch"
                    if position == 0:
                        observed_types.append(token.get("word_type"))
                elif (
                    lemmatize
                    and token.get("lemma", "").lower() != anchor
                    and token.get("text", "").lower() == anchor
                ):
                    sentence_class = "lemma_drift"
                    pin = pin or self.build_pin(rule, anchor, token)

                if sentence_class in ("word_type_mismatch", "lemma_drift"):
                    sentence_entry["match"] = match
                    sentence_entry["token"] = {
                        "text": token.get("text"),
                        "lemma": token.get("lemma"),
                        "word_type": token.get("word_type"),
                        "pos": token.get("pos"),
                        "tag": token.get("tag"),
                        "morph": token.get("morph"),
                    }
                    break

            classes.append(sentence_class or "other")
            sentence_entries.append(sentence_entry)

        # A rule gets the most severe/most actionable class observed:
        # word-type mismatch beats lemma drift beats other.
        if "word_type_mismatch" in classes:
            rule_class = "word_type_mismatch"
        elif "lemma_drift" in classes:
            rule_class = "lemma_drift"
        else:
            rule_class = "other"

        return {
            "rule": rule.pk,
            "lemma": rule.lemma,
            "language": str(rule.language),
            "word_types": rule.word_types,
            "actual_word_types": rule.actual_word_types,
            "pattern": rule.pattern,
            "entity_type": str(rule.entity_type),
            "declared_first_type": declared_type,
            "sibling_word_types": sibling_word_types,
            "class": rule_class,
            "proposed_action": self.propose_action(
                rule, rule_class, declared_type, observed_types, pin
            ),
            "sentences": sentence_entries,
        }

    def find_anchor(self, anchor, tokens):
        if not anchor:
            return None, None

        for token in tokens:
            if token.get("lemma", "").lower() == anchor:
                return token, "lemma"
        for token in tokens:
            if token.get("text", "").lower() == anchor:
                return token, "surface"

        best = None
        best_ratio = 0.0
        for token in tokens:
            for candidate in (token.get("text", ""), token.get("lemma", "")):
                ratio = difflib.SequenceMatcher(
                    None, candidate.lower(), anchor
                ).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = token
        if best is not None and best_ratio >= 0.75:
            return best, "fuzzy"

        return None, None

    def build_pin(self, rule, anchor, token):
        morph = token.get("morph") or {}
        text = token.get("text", "").lower()
        pin = {
            "language": str(rule.language),
            "text": text,
            "lemma": anchor,
            "is_plural": morph.get("Number") == "Plur",
        }

        # Identity pins (Behinderte precedent) only preserve a form against
        # drift and are always safe.
        if text == anchor:
            return pin

        # A rewriting pin changes this surface form's lemma for every rule in
        # the language. Refuse when the surface is itself a word of another
        # rule (the pin would break that rule's own matching), when it is too
        # short to be distinctive, or when it is not clearly a form of the
        # rule key (fuzzy matches like flüchtlingswelle/flüchtlingsflut or
        # the/their must go to manual adjudication instead).
        if len(text) < 3:
            return None
        if text in self.rule_tokens(str(rule.language)):
            return None
        ratio = difflib.SequenceMatcher(None, text, anchor).ratio()
        if ratio < 0.8:
            return None

        return pin

    def rule_tokens(self, language):
        if not hasattr(self, "_rule_tokens"):
            self._rule_tokens = {}
        if language not in self._rule_tokens:
            tokens = set()
            for lemma_json in Rule.objects.filter(
                language=language, is_active=True
            ).values_list("lemma_json", flat=True):
                for token in lemma_json or []:
                    tokens.add(token.lower())
            self._rule_tokens[language] = tokens
        return self._rule_tokens[language]

    def propose_action(self, rule, rule_class, declared_type, observed_types, pin):
        if rule_class == "lemma_drift" and pin:
            return {"action": "lemmatization_pin", "pin": pin}

        if rule_class != "word_type_mismatch":
            return {"action": "manual", "reason": "unclassified failure"}

        missing = sorted(
            {
                observed
                for observed in observed_types
                if observed and observed != declared_type
            }
        )

        # A sibling that already declares the observed reading means the rule
        # data is complete; the sentence just belongs to the sibling.
        sibling_types = {
            (sibling or "").strip("=~-")
            for sibling in Rule.objects.filter(
                language=rule.language, lemma=rule.lemma, is_active=True
            )
            .exclude(pk=rule.pk)
            .values_list("word_types", flat=True)
        }
        covered = [observed for observed in missing if observed in sibling_types]
        if covered and set(covered) == set(missing):
            return {"action": "move_sentence_to_sibling", "word_types": covered}

        if len(rule.lemma_json or []) != 1:
            return {"action": "manual", "reason": "multi-token rule"}

        if declared_type in CONTENT_WORD_TYPES:
            marked = MARKED_DIMENSIONS & set(rule.diversity_dimension_json or [])
            if marked:
                alternatives = (
                    rule.parent.alternatives if rule.parent else rule.alternatives
                )
                adapted = any(
                    not alternative.is_remove and not alternative.is_inspiration
                    for alternative in alternatives.all()
                )
                return {
                    "action": "empty_word_type",
                    "needs_actual_word_types": adapted,
                    "observed_types": missing,
                    "marked_dimensions": sorted(marked),
                }

            return {
                "action": "manual",
                "reason": "content word outside marked dimensions; "
                "sibling or pattern to be adjudicated",
                "observed_types": missing,
            }

        if declared_type in FUNCTION_WORD_TYPES and missing:
            return {"action": "sibling_rule", "missing_word_types": missing}

        return {"action": "manual", "reason": "no actionable observed type"}
