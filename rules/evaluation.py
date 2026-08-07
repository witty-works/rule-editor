"""Shared helpers for evaluating rules against the NLP API.

The admin form, the nightly check and the evaluation/triage commands all need
the same /debug/rule payload; keeping it here means they cannot drift apart.
"""

from django.core.exceptions import ValidationError

from rules.models import Lemmatization, fetch_json


def build_rule_payload(rule):
    """Build the /debug/rule payload for a rule, without the text.

    Callers add {"text": ...} per sentence, so the expensive part (alternative
    and lemmatization queries) runs once per rule, not once per sentence.
    """
    rule_alternatives = rule.parent.alternatives if rule.parent else rule.alternatives

    alternatives = []
    for alternative in rule_alternatives.all().order_by("order"):
        alternatives.append(
            {
                "lemma": alternative.lemma,
                "word_types": alternative.word_types_json,
                "type": str(alternative.type),
                "pluralization": str(alternative.pluralization),
                "is_inspiration": alternative.is_inspiration,
                "is_advanced": alternative.is_advanced,
                "is_remove": alternative.is_remove,
                "is_collective_noun": alternative.is_collective_noun,
                "is_gendered_noun": alternative.is_gendered_noun,
                "is_placeholder": alternative.is_placeholder,
            }
        )

    false_positives = []
    for false_positive in rule.false_positives.all():
        false_positives.append(false_positive.false_positive)

    lemmatizations = []
    for token in rule.lemma_json:
        token_lemmatizations = Lemmatization.objects.filter(
            lemma=token, language=rule.language
        ).order_by("-word_type")

        for token_lemmatization in token_lemmatizations:
            lemmatizations.append(
                {
                    "text": token_lemmatization.text,
                    "lemma": token_lemmatization.lemma,
                    "word_type": token_lemmatization.word_type,
                }
            )

    return {
        "lang": str(rule.language),
        "lemma": rule.lemma,
        "type": rule.type,
        "word_types": rule.word_types_json,
        "actual_word_types": rule.actual_word_types,
        "subcategories": rule.diversity_dimension_json,
        "alternatives": alternatives,
        "false_positives": false_positives,
        "label": rule.label,
        "pattern": rule.pattern,
        "is_pattern_match": rule.is_pattern_match,
        "entity_type": rule.entity_type,
        "pluralization": rule.pluralization,
        "lemmatizations": lemmatizations,
    }


def evaluate_sentence(payload, text):
    """Run one sentence through /debug/rule.

    Returns (matched, error): matched is True/False when the API answered,
    None when the call failed; error carries the failure text. An API error
    must never count as "did not match" — that distinction is exactly what
    check_rules' bare except loses.
    """
    try:
        response = fetch_json("/debug/rule", payload | {"text": text})
    except ValidationError as exception:
        return None, str(exception.message)
    except Exception as exception:  # network/timeout
        return None, str(exception)

    if not isinstance(response, list):
        return None, "unexpected response: %r" % (response,)

    return len(response) > 0, ""


def fetch_api_version():
    """Fetch the /version stamp of the NLP API the evaluation runs against."""
    return fetch_json("/version")


def analyze_text(lang, text, detailed=False):
    """Token-level spaCy reading of a text via /debug/spacy.

    Returns (auto_word_types, tokens): the auto-detected word type string and
    the token dicts (text/lemma/word_type, plus pos/tag/morph when detailed).
    """
    import requests as requests_lib

    path = "/debug/spacy?lang=%s&text=%s&detailed=%s" % (
        requests_lib.utils.quote(lang),
        requests_lib.utils.quote(text),
        "true" if detailed else "false",
    )
    result = fetch_json(path)

    meta = result.pop(0)
    auto_word_types = meta.get("auto-detected word type", "")
    if detailed and result and "noun chunks" in result[0]:
        result.pop(0)

    return auto_word_types, result
