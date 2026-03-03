"""Shared model and field name constants for import/export utilities.

Keeping these in one place reduces duplication and prevents typos.
"""

# App model labels
CATEGORY = "rules.category"
DIV_DIM = "rules.diversitydimension"
SOURCE = "rules.source"
RULE = "rules.rule"
RULE_DIV_DIM = "rules.rulediversitydimension"
ALTERNATIVE = "rules.alternative"
TRAINING_SENTENCE = "rules.trainingsentence"
FALSE_POSITIVE = "rules.falsepositive"
LEMMATIZATION = "rules.lemmatization"
EN_NOUN = "rules.englishnoun"
EN_VERB = "rules.englishverb"
EN_ADJ = "rules.englishadjective"
DE_NOUN = "rules.germannoun"
DE_VERB = "rules.germanverb"
DE_ADJ = "rules.germanadjective"
FR_NOUN = "rules.frenchnoun"
RULE_STRUCTURE_EVAL = "rules.rulestructureevaluation"

# External app labels
AUTH_USER = "auth.user"
AUTH_SESSION = "auth.session"

# Common field names
FIELD_RULE = "rule"
FIELD_CREATEDBY = "createdby"
FIELD_OWNEDBY = "ownedby"

# Sets and sequences used across scripts
USER_FIELD_NAMES = {FIELD_CREATEDBY, FIELD_OWNEDBY}
USER_FIELDS_DB = {f"{FIELD_CREATEDBY}_id", f"{FIELD_OWNEDBY}_id"}

IMPORT_ORDER = [
    CATEGORY,
    DIV_DIM,
    SOURCE,
    RULE,
    RULE_DIV_DIM,
    ALTERNATIVE,
    TRAINING_SENTENCE,
    FALSE_POSITIVE,
    LEMMATIZATION,
    EN_NOUN,
    EN_VERB,
    EN_ADJ,
    DE_NOUN,
    DE_VERB,
    DE_ADJ,
    FR_NOUN,
    RULE_STRUCTURE_EVAL,
]

MODELS_WITH_USER_REFS = {
    CATEGORY,
    DIV_DIM,
    SOURCE,
    RULE,
    ALTERNATIVE,
    TRAINING_SENTENCE,
    FALSE_POSITIVE,
    LEMMATIZATION,
    EN_NOUN,
    EN_VERB,
    EN_ADJ,
    DE_NOUN,
    DE_VERB,
    DE_ADJ,
    FR_NOUN,
    RULE_STRUCTURE_EVAL,
}

# ------------------------------------------------------------
# Centralized export model lists and table mappings
# These are used by multiple export commands/scripts.
# ------------------------------------------------------------

# Export lists for Django apps.get_model usage (Model class names, not fixture labels)
EXPORT_MODELS_BASE = [
    "rules.Category",
    "rules.DiversityDimension",
    "rules.Source",
]

EXPORT_MODELS_MAIN = [
    "rules.Rule",
    "rules.RuleDiversityDimension",
    "rules.Alternative",
    "rules.TrainingSentence",
    "rules.FalsePositive",
    "rules.Lemmatization",
]

EXPORT_MODELS_LINGUISTIC = [
    "rules.EnglishNoun",
    "rules.EnglishVerb",
    "rules.EnglishAdjective",
    "rules.GermanNoun",
    "rules.GermanVerb",
    "rules.GermanAdjective",
    "rules.FrenchNoun",
]

EXPORT_MODELS_EVALUATIONS = [
    "rules.RuleStructureEvaluation",
]

# Default order (base + main + linguistic + evaluations)
EXPORT_MODELS_ORDER = (
    EXPORT_MODELS_BASE
    + EXPORT_MODELS_MAIN
    + EXPORT_MODELS_LINGUISTIC
    + EXPORT_MODELS_EVALUATIONS
)

# Mapping of DB table names to fixture model labels (lowercase) for standalone exports
DB_TABLE_TO_MODEL = {
    "rules_category": CATEGORY,
    "rules_diversitydimension": DIV_DIM,
    "rules_source": SOURCE,
    "rules_rule": RULE,
    "rules_alternative": ALTERNATIVE,
    "rules_trainingsentence": TRAINING_SENTENCE,
    "rules_falsepositive": FALSE_POSITIVE,
    "rules_lemmatization": LEMMATIZATION,
    "rules_englishnoun": EN_NOUN,
    "rules_englishverb": EN_VERB,
    "rules_englishadjective": EN_ADJ,
    "rules_germannoun": DE_NOUN,
    "rules_germanverb": DE_VERB,
    "rules_germanadjective": DE_ADJ,
    "rules_frenchnoun": FR_NOUN,
    "rules_rulestructureevaluation": RULE_STRUCTURE_EVAL,
    "rules_rulediversitydimension": RULE_DIV_DIM,
}

# Reverse mapping (fixture model label -> DB table name)
MODEL_TO_DB_TABLE = {v: k for k, v in DB_TABLE_TO_MODEL.items()}
