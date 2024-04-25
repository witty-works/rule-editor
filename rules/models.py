from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.conf import settings

from django_enum import EnumField
from taggit.managers import TaggableManager
from computedfields.models import ComputedFieldsModel, computed

from german_nouns.lookup import Nouns
from inflex import Noun, Verb, Adjective
from bs4 import BeautifulSoup

import emoji

import requests
from requests.auth import HTTPBasicAuth


allowed_word_types = ["n", "pron", "a", "adv", "v", "conj", "emoji", "num", "card"]


def fetch_json(path, data=None):
    url = settings.NLP_API + path

    auth = (
        HTTPBasicAuth(settings.NLP_API_USER, settings.NLP_API_PASSWORD)
        if settings.NLP_API_USER is not None
        else None
    )

    if not bool(settings.NLP_API_USER):
        requests.packages.urllib3.disable_warnings()

    if data is None:
        r = requests.get(url, auth=auth, timeout=5)
    else:
        r = requests.post(url, json=data, auth=auth, timeout=5)

    try:
        if r.status_code != 200:
            body = r.json()
            error = body["detail"] if "detail" in body else r.text
            raise ValidationError(url + ": " + str(error))

        return r.json()
    except Exception as e:
        raise ValidationError(url + ": " + str(e))


def strip_non_alpha(text):
    return "".join(filter(str.isalpha, text))


class LanguageEnum(models.TextChoices):
    EN = "en", "English"
    DE = "de", "German"
    FR = "fr", "French"


class GenderTypeEnum(models.TextChoices):
    NONE = ""
    NEUTER = "neuter"
    FEMININE = "feminine"
    MASCULINE = "masculine"


class PluralizationEnum(models.TextChoices):
    DEFAULT = "default"
    SINGULAR_ONLY = "singular_only"
    PLURAL_ONLY = "plural_only"


class AlternativeTypeEnum(models.TextChoices):
    DEFAULT = "default"
    PERSON_FIRST = "person_first"
    IDENTITY_FIRST = "identity_first"


class RuleTypeEnum(models.TextChoices):
    DEFAULT = "default"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    SUBSTRING = "substring"


class EntityTypeEnum(models.TextChoices):
    DEFAULT = "default"
    NAME = "name"
    NON_NAME = "non_name"
    PERSON = "person"
    NON_PERSON = "non_person"
    NUMBER = "number"
    DATETIME = "datetime"


class RuleLabelEnum(models.TextChoices):
    DEFAULT = "default"
    NOT_FOR_PEOPLE = "not_for_people"
    BE_SPECIFIC = "be_specific"
    NAME_DISABILITY = "name_disability"
    ONLY_IF_GENDER_IDENTITY_RELEVANT = "only_if_gender_identity_relevant"
    NOT_FOR_NON_COMBAT = "not_for_non_combat"
    ASK_FOR_PREFERENCE = "ask_for_preference"
    ASK_ABOUT_TRADITIONS = "ask_about_traditions"
    ONLY_WHEN_REFERENCING_RELIGIOUS_PRACTICE = (
        "only_when_referencing_religious_practice"
    )
    DONT_USE_FOR_SUBSTANCE_USE = "dont_use_for_substance_use"
    DONT_USE_TO_DESCRIBE_QUALITY = "dont_use_to_describe_quality"
    USE_IN_TECH_ONLY = "use_in_tech_only"


class AutoDateTimeField(models.DateTimeField):
    def pre_save(self, model_instance, add):
        return timezone.now()


class BaseModel(models.Model):
    id = models.AutoField(primary_key=True, unique=True, editable=False)

    class Meta:
        abstract = True


class BaseTimestampedModel(BaseModel):
    created_at = models.DateField(default=timezone.now, editable=False)
    updated_at = AutoDateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True


class BaseCreatedByModel(BaseModel):
    createdby = models.ForeignKey(
        User, null=True, editable=False, on_delete=models.SET_NULL
    )

    class Meta:
        abstract = True


class BaseCommentableModel(BaseModel):
    comment = models.TextField(
        null=True,
        blank=True,
        help_text="Any useful comments to keep for internal purposes.",
    )

    class Meta:
        abstract = True


class Source(BaseTimestampedModel, BaseCommentableModel, BaseCreatedByModel):
    def __str__(self):
        return self.name

    def clean(self):
        errors = {}

        if self.url:
            self.url = self.url.strip()
            self.url = None if self.url == "" else self.url

        if self.url is not None:
            validator = URLValidator()
            try:
                validator(self.url)
            except ValidationError as exception:
                errors["url"] = (
                    "URL must either be empty or a valid URL: " + exception.message
                )

        if len(errors):
            raise ValidationError(errors)

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Some short text identifier for the source",
    )
    url = models.CharField(
        max_length=255, null=True, blank=True, help_text="URL to the source"
    )
    reference = models.TextField(
        null=True,
        blank=True,
        help_text="A reference to a non URL source, f.e. ISBN, journal name/number etc.",
    )
    tags = TaggableManager(blank=True)


class BaseSourcedModel(BaseModel):
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True


class BaseLemmaModel(ComputedFieldsModel, BaseModel):
    def tokenize(self):
        if self.lemma == "-":
            return ["-"], ["-"], ""

        language = requests.utils.quote(self.language)
        text = requests.utils.quote(self.lemma.strip("~"))
        path = f"/debug/spacy?lang={language}&text={text}"
        result = fetch_json(path)
        word_types = result.pop(0)
        word_types = "" if "word_type" not in word_types else word_types["word_type"]
        tokens = []
        lemmas = []
        for token in result:
            tokens.append(token["text"])
            lemmas.append(token["lemma"])

        return tokens, lemmas, word_types

    def parse_word_types(self):
        if self.word_types is None or len(self.word_types) == 0:
            return None

        path = f"/parse-word-types?lang={requests.utils.quote(self.language)}&text={requests.utils.quote(self.lemma)}&word_types={requests.utils.quote(self.word_types)}"
        return fetch_json(path)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        try:
            self.tokenized, lemmas, word_types = self.tokenize()
        except ValidationError as exception:
            errors["lemma"] = "Lemma could not be tokenized: " + exception.message

        if self.is_active:
            try:
                self.parsed_word_types = self.parse_word_types()
            except ValidationError as exception:
                errors["word_types"] = (
                    "Word_types validation failed: " + exception.message
                )

        if len(errors):
            raise ValidationError(errors)

    class Meta:
        abstract = True

    tokenized = None
    parsed_word_types = None

    lemma = models.CharField(
        max_length=255,
        help_text="Lemma is one or multiple words (tokens) either in lemmatized form or not (depending on the word_types)",
    )

    @computed(
        models.JSONField(default=dict),
        depends=[
            ("self", ["lemma"]),
        ],
    )
    def lemma_json(self):
        return self.tokenized

    word_types = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="'|' separated list of word types used for matching the rule (n, pron, a, adv, v, conj, emoji, num, card) and optional modifiers: '=' case sensitive unlemmatized, '~' case insensitive unlemmatize, '-' case sensitive lemmatized",
    )

    @computed(
        models.JSONField(default=dict),
        depends=[
            ("self", ["word_types"]),
        ],
    )
    def word_types_json(self):
        return [] if self.parsed_word_types is None else self.parsed_word_types

    is_active = models.BooleanField(default=True)
    label = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Additional label to add to the short explanation/alternative",
    )


class Category(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Machine name of the category",
    )


class DiversityDimension(
    ComputedFieldsModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
):
    def __str__(self):
        return self.name

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Machine name of the diversity dimension (with optional '_advanced' suffix)",
    )
    external_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Public name of the diversity dimension",
    )
    parent_name = models.CharField(
        max_length=255,
        help_text="Machine name of the diversity dimension (without optional '_advanced' suffix)",
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, help_text="Top-level category"
    )
    proficiency_level = models.CharField(
        max_length=255,
        help_text="Proficiency level of the diversity dimension ('inclusive', 'unconscious_bias', 'openly_discriminating', ..)",
    )
    has_en_rules = models.BooleanField(
        default=False,
        help_text="If the diversity dimension has English rules",
    )
    has_de_rules = models.BooleanField(
        default=False,
        help_text="If the diversity dimension has German rules",
    )
    url_en = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="URL to the category page in English",
    )
    url_de = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="URL to the category page in German",
    )
    has_rules = models.BooleanField(
        default=True,
        help_text="If the diversity dimension has rules (or if rules are hardcoded or advanced alternatives only)",
    )

    @computed(
        models.BooleanField(null=True, blank=True),
        depends=[
            ("self", ["name"]),
        ],
    )
    def is_advanced(self):
        return self.name.endswith("_advanced")


class Rule(
    BaseLemmaModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    class Meta:
        unique_together = (
            ("language", "lemma", "word_types", "type", "pluralization"),
        )
        indexes = [
            models.Index(
                fields=[
                    "is_auto_generated",
                    "is_active",
                    "language",
                    "type",
                    "first_token",
                    "first_is_word_type_lemmatize",
                    "first_is_word_type_lower_case",
                ]
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.emoji:
            self.emoji = self.emoji.strip()
            self.emoji = None if self.emoji == "" else self.emoji

        if self.emoji is not None:
            self.emoji = self.emoji.strip()
            if not emoji.is_emoji(self.emoji):
                errors["emoji"] = (
                    "Emoji must either be empty or a valid emoji character: "
                    + self.emoji
                )

        if self.url:
            self.url = self.url.strip()
            self.url = None if self.url == "" else self.url

        if self.parent:
            self.language = self.parent.language

        if self.url is not None:
            validator = URLValidator()
            try:
                validator(self.url)
            except ValidationError as exception:
                errors["url"] = (
                    "URL must either be empty or a valid URL: " + exception.message
                )

        if self.tokenized is not None:
            if self.type != "default" and len(self.tokenized) > 1:
                errors["type"] = "Rules with a non default type can only have one token"

            if self.actual_word_types is not None and self.actual_word_types != "":
                actual_word_types = self.actual_word_types.split("|")
                if len(self.tokenized) != len(actual_word_types):
                    errors["actual_word_types"] = (
                        f"Number of word types does not match token count {len(self.tokenized)}"
                    )
                else:
                    word_type_delta = list(
                        set(actual_word_types) - set(allowed_word_types)
                    )
                    if len(word_type_delta):
                        word_type_delta = ", ".join(word_type_delta)
                        errors["actual_word_types"] = (
                            f"Unsupported word types: {word_type_delta}"
                        )

        if len(errors):
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.lemma[0:40]} - {self.word_types} ({self.language})"

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)
    tags = TaggableManager(blank=True, related_name="RuleTags")

    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.CASCADE
    )
    links = models.ManyToManyField("self", symmetrical=True, blank=True)

    pattern = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional pattern to define word types before and after the lemma. Syntax 'l' for the lemma. '*' means zero or many, '+' means once or many.",
    )
    is_pattern_match = models.BooleanField(
        default=False,
        help_text="if the pattern should expand the matched text or if it is just used to avoid false positives",
    )

    text_id = models.CharField(
        max_length=255,
        help_text="String used to identify the rule, f.e. in the top words of the analytics",
    )

    type = EnumField(
        RuleTypeEnum,
        default=RuleTypeEnum.DEFAULT,
        help_text="Should the rule check on part of the lemma (only 'default' allows multiple token lemma).",
    )

    entity_type = EnumField(
        EntityTypeEnum,
        default=RuleTypeEnum.DEFAULT,
        help_text="If the rule should only match on a specific entity type (name, non_name, person, non_person, number, datetime).",
    )

    label_type = EnumField(
        RuleLabelEnum,
        default=RuleLabelEnum.DEFAULT,
        help_text="Quick selections for custom labels (only change from 'default' if label is empty).",
    )

    pluralization = EnumField(
        PluralizationEnum,
        default=PluralizationEnum.DEFAULT,
        help_text="Show alternative in case rule triggered on singular/plural/both",
    )

    is_context_aware = models.BooleanField(
        default=False,
        help_text="Uses custom machine learning model to determine if to highlight in the given context.",
    )
    is_marked_for_review = models.BooleanField(
        default=False, help_text="Rule should be reviewed"
    )
    is_auto_generated = models.BooleanField(
        default=False, help_text="Rule was auto generated", null=True
    )
    generated_at = models.DateTimeField(
        null=True, blank=True, help_text="When the rule was auto generated"
    )
    source_rule = models.CharField(
        max_length=1000,
        blank=True,
        help_text="Rule that was used to generate this rule",
    )
    has_failing_training_sentence = models.BooleanField(
        default=False,
        help_text="If one of the training sentences is not triggering the given rule as expected",
    )
    is_hr_rule = models.BooleanField(
        default=False,
        help_text="If this rule is enabled only for the HR-addon",
    )

    diversity_dimensions = models.ManyToManyField(
        DiversityDimension, through="RuleDiversityDimension"
    )

    ownedby = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="owner"
    )

    explanation = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Override the diversity dimension text with a custom explanation",
    )
    emoji = models.CharField(
        max_length=5,
        null=True,
        blank=True,
        help_text="Override the diversity dimension emoji with a custom emoji",
    )
    url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Override the diversity dimension URL with a custom URL",
    )

    actual_word_types = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional '|' separated list of word types matching the actual word types",
    )

    sanctions = models.ManyToManyField(
        Source, blank=True, related_name="rule_sanctions"
    )

    @computed(
        models.CharField(max_length=255, null=True, blank=True),
        depends=[
            ("self", ["lemma_json"]),
            ("self", ["word_types"]),
        ],
    )
    def first_token(self):
        if self.lemma_json is None or len(self.lemma_json) == 0:
            return None

        first_token = self.lemma_json[0]
        if (
            self.parsed_word_types is not None
            and len(self.parsed_word_types)
            and self.parsed_word_types[0]["lower_case"]
        ):
            first_token = first_token.lower()

        return first_token

    @computed(
        models.CharField(max_length=255, null=True, blank=True),
        depends=[
            ("self", ["word_types"]),
        ],
    )
    def first_word_type(self):
        if self.parsed_word_types is None or len(self.parsed_word_types) == 0:
            return None

        return self.parsed_word_types[0]["word_type"]

    @computed(
        models.BooleanField(null=True, blank=True),
        depends=[
            ("self", ["word_types"]),
        ],
    )
    def first_is_word_type_lemmatize(self):
        if self.parsed_word_types is None or len(self.parsed_word_types) == 0:
            return None

        return self.parsed_word_types[0]["lemmatize"]

    @computed(
        models.BooleanField(null=True, blank=True),
        depends=[
            ("self", ["word_types"]),
        ],
    )
    def first_is_word_type_lower_case(self):
        if self.parsed_word_types is None or len(self.parsed_word_types) == 0:
            return None

        return self.parsed_word_types[0]["lower_case"]

    @computed(
        models.BooleanField(null=True, blank=True),
        depends=[
            ("training_sentences", ["text"]),
        ],
    )
    def has_training_sentences(self):
        return bool(len(self.training_sentences.all())) if self.id else False

    @computed(
        models.JSONField(default=dict),
        depends=[
            ("self", ["parent"]),
            ("diversity_dimensions", ["name"]),
            ("rulediversitydimension", ["diversity_dimension"]),
        ],
        prefetch_related=["diversity_dimensions"],
    )
    def diversity_dimension_json(self):
        diversity_dimensions = []
        if self.pk:
            obj = self.parent if self.parent else self

            for diversity_dimension in obj.diversity_dimensions.all().order_by(
                "rulediversitydimension__order"
            ):
                diversity_dimensions.append(diversity_dimension.name)

            for child in self.children.all():
                child.diversity_dimension_json = diversity_dimensions
                child.save()

        return diversity_dimensions

    @computed(
        models.PositiveIntegerField(null=True, blank=True),
        depends=[
            ("self", ["lemma"]),
        ],
    )
    def lemma_length(self):
        if self.lemma is None:
            return 0

        return len(self.lemma)


class RuleStructureEvaluation(BaseCreatedByModel):
    unique_integer_generator = 0

    rule = models.ForeignKey(
        Rule,
        on_delete=models.CASCADE,
        related_name="evaluations",
    )

    rule_source_rule = models.TextField(
        null=True, blank=True, help_text="Rule that was used to generate this rule"
    )

    rule_inclusiveness = models.IntegerField(
        choices=[(0, "yes"), (1, "no"), (2, "unsure")],
        default=0,
        help_text="Is this rule trigger uninclusive",
    )

    rule_carries_same_meaning = models.IntegerField(
        choices=[(0, "yes"), (1, "no"), (2, "unsure")],
        default=0,
        help_text="Does this rule carry the same meaning as the source rule? ",
    )

    rule_fits_diversity_dimension = models.IntegerField(
        choices=[(0, "yes"), (1, "no"), (2, "unsure")],
        default=0,
        help_text="Does this rule fit the diversity dimension? ",
    )

    rule_importance = models.IntegerField(
        choices=[
            (1, "not important"),
            (2, "less important"),
            (3, "important"),
            (4, "very important"),
            (5, "extremely important"),
        ],
        default=3,
        help_text="How important is it that we have this rule?",
    )

    rule_inspiration = models.IntegerField(
        choices=[(0, "yes"), (1, "no")],
        default=1,
        help_text="Does this rule inspire the creation of another rule (if yes, write it in notes)?",
    )

    rule_notes = models.TextField(
        null=True, blank=True, help_text="Interesting notes/observations on rule"
    )

    alternative_1_inclusiveness = models.IntegerField(
        choices=[(0, "yes"), (1, "no"), (2, "unsure"), (3, "not applicable")],
        default=0,
        help_text="Is alternative 1 more inclusive than rule trigger",
    )

    alternative_2_inclusiveness = models.IntegerField(
        choices=[(0, "yes"), (1, "no"), (2, "unsure"), (3, "not applicable")],
        default=0,
        help_text="Is alternative 2 m0re inclusive than rule trigger",
    )

    alternative_3_inclusiveness = models.IntegerField(
        choices=[(0, "yes"), (1, "no"), (2, "unsure"), (3, "not applicable")],
        default=0,
        help_text="Is alternative 3 more inclusive than rule trigger",
    )

    alternative_1_quality = models.IntegerField(
        choices=[
            (1, "Poor"),
            (2, "Fair"),
            (3, "Good"),
            (4, "Very Good"),
            (5, "Excellent"),
            (6, "Not applicable"),
        ],
        default=3,
        help_text="Rate the quality of alternative 1",
    )

    alternative_2_quality = models.IntegerField(
        choices=[
            (1, "Poor"),
            (2, "Fair"),
            (3, "Good"),
            (4, "Very Good"),
            (5, "Excellent"),
            (6, "Not applicable"),
        ],
        default=3,
        help_text="Rate the quality of alternative 2",
    )

    alternative_3_quality = models.IntegerField(
        choices=[
            (1, "Poor"),
            (2, "Fair"),
            (3, "Good"),
            (4, "Very Good"),
            (5, "Excellent"),
            (6, "Not applicable"),
        ],
        default=3,
        help_text="Rate the quality of alternative 3",
    )
    alternative_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Interesting notes/observations on alternatives",
    )

    training_sentence_1_fits_context = models.CharField(
        max_length=255,
        choices=[
            ("yes", "Yes"),
            ("no", "No"),
            ("unsure", "Unsure"),
            ("not applicable", "Not Applicable"),
        ],
        default="unsure",
        help_text="Does training sentence 1 make sense in context of the rule?",
    )

    training_sentence_2_fits_context = models.CharField(
        max_length=255,
        choices=[
            ("yes", "Yes"),
            ("no", "No"),
            ("unsure", "Unsure"),
            ("not applicable", "Not Applicable"),
        ],
        default="unsure",
        help_text="Does training sentence 2 make sense in context of the rule?",
    )

    written_by_human = models.CharField(
        max_length=255,
        choices=[("yes", "Yes"), ("no", "No"), ("unsure", "Unsure")],
        default="unsure",
        help_text="Would you believe that the sentences were written by a human?",
    )

    notes_training_sentences = models.TextField(
        null=True,
        blank=True,
        help_text="Interesting notes/observations on training sentences",
    )

    class Meta:
        verbose_name = "Rule Evaluation"
        verbose_name_plural = "Rule Evaluations"

    def __str__(self):
        text = f"Rule {self.rule}"
        if self.createdby is not None:
            text += f" evaluated by {self.createdby.username}"

        return text


class RuleDiversityDimension(BaseTimestampedModel):
    class Meta:
        unique_together = (("rule", "diversity_dimension"),)
        ordering = ("order",)

    def __str__(self):
        return str(self.diversity_dimension)

    order = models.PositiveIntegerField("order", db_index=True)

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)
    diversity_dimension = models.ForeignKey(
        DiversityDimension, on_delete=models.CASCADE
    )


class Alternative(
    BaseLemmaModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    class Meta:
        ordering = ("order",)
        indexes = [
            models.Index(
                fields=[
                    "is_active",
                    "rule_id",
                    "is_placeholder",
                    "is_inspiration",
                    "pluralization",
                    "order",
                ]
            ),
        ]

    def __str__(self):
        return "[REMOVE]" if self.is_remove else self.lemma[0:50]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        if self.is_remove:
            self.lemma = "-"
            self.word_types = ""
        else:
            words = self.lemma.split()
            gendered_noun_found = False
            for word in words:
                if word.endswith("~"):
                    if not word.startswith("~"):
                        raise ValidationError(
                            f"Word in lemma may not end with '~' for '{self.lemma}'"
                        )

                    gendered_noun_found = True
                    if not self.is_gendered_noun:
                        raise ValidationError(
                            f"Gendered noun markers detected (noun with '~' prefix+suffix) but alternative not marked as 'gendered noun' for '{self.lemma}'"
                        )

        if self.is_gendered_noun and not gendered_noun_found:
            raise ValidationError(
                f"No Gendered noun markers detected (noun with '~' prefix+suffix) but alternative marked as 'gendered noun' for '{self.lemma}'"
            )

        return super().clean()

    order = models.PositiveIntegerField("order", db_index=True)

    rule = models.ForeignKey(
        Rule, related_name="alternatives", on_delete=models.CASCADE
    )

    type = EnumField(AlternativeTypeEnum, default=AlternativeTypeEnum.DEFAULT)
    pluralization = EnumField(
        PluralizationEnum,
        default=PluralizationEnum.DEFAULT,
        help_text="Show alternative in case rule triggered on singular/plural/both",
    )
    is_remove = models.BooleanField(
        default=False,
        help_text="User will be offered to remove the words instead of a text alternative",
    )
    is_inspiration = models.BooleanField(
        default=False,
        help_text="Alternative will be marked as inspiration, hidden if user has inspiration disabled. Also never adjusted for grammatical correctness",
    )
    is_advanced = models.BooleanField(
        default=False,
        help_text="Only show if user has diversity dimension enabled at advanced level.",
    )
    is_collective_noun = models.BooleanField(
        default=False,
        help_text="If this is a collective noun, which means do not pluralize.",
    )
    is_gendered_noun = models.BooleanField(
        default=False,
        help_text="If this is a alternative contains gendered nouns and non gendered variations should be generated.",
    )
    sanctions = models.ManyToManyField(
        Source, blank=True, related_name="alternative_sanctions"
    )

    @computed(
        models.BooleanField(default=False),
        depends=[
            ("self", ["lemma"]),
        ],
    )
    def is_placeholder(self):
        return "((" in self.lemma and "))" in self.lemma

    @computed(
        EnumField(LanguageEnum, default=LanguageEnum.EN),
        depends=[
            ("rule", ["language"]),
        ],
    )
    def language(self):
        return self.rule.language

    tags = TaggableManager(blank=True)


class TrainingSentence(
    ComputedFieldsModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    def __str__(self):
        return self.text

    rule = models.ForeignKey(
        Rule, related_name="training_sentences", on_delete=models.CASCADE
    )

    text = models.TextField(null=True, blank=True)

    is_false_positive = models.BooleanField(
        default=False, help_text="If sentences should not trigger the rule"
    )
    is_training_data = models.BooleanField(
        default=False,
        help_text="If sentences should be used for the custom machine learning model",
    )
    alternative_expected = models.CharField(
        max_length=255,
        blank=True,
        help_text="Alternative expected to be included in the alternative list",
    )
    is_on_website = models.BooleanField(
        default=False,
        help_text="If the example is shown on the website",
    )

    tags = TaggableManager(blank=True)


class FalsePositive(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.false_positive

    class Meta:
        unique_together = (("rule", "false_positive"),)

    rule = models.ForeignKey(
        Rule, related_name="false_positives", on_delete=models.CASCADE
    )

    false_positive = models.CharField(max_length=255)


class Lemmatization(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.text

    class Meta:
        unique_together = (("language", "text"),)

    text = models.CharField(max_length=255, help_text="Source text")
    language = EnumField(LanguageEnum, default=LanguageEnum.EN)
    lemma = models.CharField(
        max_length=255, help_text="Lemma used for the given source text"
    )
    is_plural = models.BooleanField(default=False, help_text="If the text is plural")


class EnglishVerb(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    def fill_declensions_standard(self, _=None):
        return self.fill_declensions()

    def fill_declensions(self, _=None):
        inflex = Verb(self.base_form)
        self.past_tense = inflex.past()
        self.past_participle = inflex.past_part()
        self.present_participle = inflex.pres_part()
        self.third_person_singular = inflex.singular()

        self.save()

        message = "English verb declension data has been filled."
        return False, message

    base_form = models.CharField(max_length=255, unique=True)
    past_tense = models.CharField(max_length=255, null=True, blank=True)
    past_participle = models.CharField(max_length=255, null=True, blank=True)
    present_participle = models.CharField(max_length=255, null=True, blank=True)
    third_person_singular = models.CharField(max_length=255, null=True, blank=True)


class EnglishAdjective(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    def fill_declensions_standard(self, _=None):
        inflex = Adjective(self.base_form)
        self.comparative = inflex.comparative()
        self.superlative = inflex.superlative()

        self.save()

        message = "Filled English adjective with standard rules"
        return False, message

    def fill_declensions(self, _=None):
        self.is_absolute = self.base_form[0].isupper()
        if self.is_absolute == False:
            soup = get_soup(self.base_form)
            if soup is None:
                message = "Unable to download English adjective Wikitionary data"
                return True, message

            element = soup.find("span", {"id": "Adjective"})
            if element is None:
                message = "English adjective data missing on Wikitionary"
                return True, message

            element = element.find_next("p")

            uncomparable = element.find(
                "a", {"href": "/wiki/Appendix:Glossary#uncomparable"}
            )
            if uncomparable:
                self.is_absolute = True
            else:
                not_generally = element.select_one('i:-soup-contains("not generally")')
                if not_generally:
                    self.is_absolute = True
                else:
                    element.find("a", {"href": "/wiki/Appendix:Glossary#comparative"})
                    comparative = element.find(
                        "a", {"href": "/wiki/Appendix:Glossary#comparative"}
                    )
                    self.is_absolute = not bool(comparative)

        if self.is_absolute:
            self.comparative = self.base_form
            self.superlative = self.base_form
        else:
            self.fill_declensions_standard()

        self.save()

        message = "English adjective declension data has been filled."
        return False, message

    def clean(self):
        super().clean()

        if self.is_absolute:
            self.comparative = self.base_form
            self.superlative = self.base_form

    base_form = models.CharField(max_length=255, unique=True)
    comparative = models.CharField(max_length=255, null=True, blank=True)
    superlative = models.CharField(max_length=255, null=True, blank=True)
    is_absolute = models.BooleanField(
        default=False, help_text="If adjective is in an absolute"
    )


class EnglishNoun(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    def fill_declensions_standard(self, _=None):
        inflex = Noun(self.base_form)
        self.plural = inflex.plural()
        self.save()

        message = "English noun declension data has been filled."
        return False, message

    def fill_declensions(self, _=None):
        return self.fill_declensions_standard()

    base_form = models.CharField(max_length=255, unique=True)
    plural = models.CharField(max_length=255, null=True, blank=True)
    plural_2 = models.CharField(max_length=255, null=True, blank=True)


def get_soup(base_form, source="wikitionary", flexion=False):
    try:
        if source == "wikitionary":
            url = (
                "https://de.wiktionary.org/wiki/Flexion:"
                if flexion
                else "https://de.wiktionary.org/wiki/"
            )
        else:
            url = "https://www.verbformen.de/konjugation/?w="

        response = requests.get(url + base_form)
        return BeautifulSoup(response.text, "html.parser")
    except requests.exceptions.ConnectionError:
        pass

    return None


class GermanVerb(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    def german_verb_splittable(self):
        splittable_words = {
            "durch": [
                "durchbeißen",
                "durchbeissen",
                "durchblasen",
                "durchblättern",
                "durchbrausen",
                "durchdringen",
                "durchfahren",
                "durchfallen",
                "durchfeiern",
                "durchgehen",
                "durchglühen",
                "durchkämpfen",
                "durchklettern",
                "durchkramen",
                "durchkriechen",
                "durchradeln",
                "durchrauschen",
                "durchrennen",
                "durchrieseln",
                "durchrinnen",
                "durchschallen",
                "durchscheinen",
                "durchschlafen",
                "durchschleichen",
                "durchschnüffeln",
                "durchschwitzen",
                "durchsetzen",
                "durchspringen",
                "durchsteigen",
                "durchstreichen",
                "durchwachen",
                "durchwachsen",
                "durchwärmen",
                "durchwaten",
                "durchziehen",
            ],
            "fremd": [
                "fremdschämen",
            ],
            "über": [
                "überbeanspruchen",
                "überbehüten",
                "überbeißen",
                "überbeissen",
                "überbekommen",
                "überbelasten",
                "überbelegen",
                "überbelichten",
                "überbetonen",
                "überbewerten",
                "überbezahlen",
                "überbleiben",
                "überdramatisieren",
                "übererfüllen",
                "überessen",
                "überfließen",
                "überfliessen",
                "übergehen",
                "überhandnehmen",
                "überhängen",
                "überkippen",
                "überkippen",
                "überkochen",
                "überlaufen",
                "überleiten",
                "überpflanzen",
                "überschießen",
                "überschiessen",
                "überschlagen",
                "übersprudeln",
                "übersprühen",
                "überstechen",
                "übertreten",
                "übertun",
                "überversichern",
                "überversorgen",
                "überwallen",
                "überwerfen",
                "übrigbehalten",
                "übrigbleiben",
                "übrighaben",
                "übriglassen",
            ],
            "offen": [
                "offenbleiben",
                "offenhalten",
                "offenlassen",
                "offenlegen",
                "offenliegen",
                "offenstehen",
            ],
            "um": [
                "umackern",
                "umadressieren",
                "umändern",
                "umarbeiten",
                "umbauen",
                "umbehalten",
                "umbenennen",
                "umbeschreiben",
                "umbesinnen",
                "umbestellen",
                "umbetten",
                "umbiegen",
                "umbilden",
                "umbinden",
                "umblasen",
                "umblättern",
                "umblicken",
                "umbranden",
                "umbrausen",
                "umbrechen",
                "umbringen",
                "umbuchen",
                "umdatieren",
                "umdecken",
                "umdefinieren",
                "umdeklarieren",
                "umdekorieren",
                "umdenken",
                "umdeuten",
                "umdichten",
                "umdirigieren",
                "umdisponieren",
                "umdrehen",
                "umdrucken",
                "umdrücken",
                "umentscheiden",
                "umerziehen",
                "umetikettieren",
                "umfallen",
                "umfälschen",
                "umfärben",
                "umfinanzieren",
                "umfirmieren",
                "umflaggen",
                "umformatieren",
                "umformulieren",
                "umfragen",
                "umfrisieren",
                "umfüllen",
                "umfunktionieren",
                "umgehen",
                "umgestalten",
                "umgewöhnen",
                "umgießen",
                "umgiessen",
                "umgraben",
                "umgründen",
                "umgruppieren",
                "umgucken",
                "umhaben",
                "umhacken",
                "umhängen",
                "umhauen",
                "umheben",
                "umherblicken",
                "umhinkönnen",
                "umhören",
                "uminterpretieren",
                "umkehren",
                "umkippen",
                "umklappen",
                "umknicken",
                "umkommen",
                "umkonstruieren",
                "umkopieren",
                "umkrempeln",
                "umladen",
                "umlagern",
                "umlassen",
                "umlauten",
                "umlegen",
                "umleiten",
                "umlenken",
                "umlernen",
                "ummachen",
                "ummelden",
                "ummodeln",
                "ummünzen",
                "umnehmen",
                "umnehmen",
                "umnutzen",
                "umoperieren",
                "umordnen",
                "umorganisieren",
                "umorientieren",
                "umpacken",
                "umparken",
                "umpflügen",
                "umplanen",
                "umpolen",
                "umprägen",
                "umprogrammieren",
                "umpumpen",
                "umpusten",
                "umquartieren",
                "umrangieren",
                "umräumen",
                "umrechnen",
                "umrennen",
                "umrubeln",
                "umrühren",
                "umrüsten",
                "umsäbeln",
                "umsacken",
                "umsägen",
                "umsatteln",
                "umschaffen",
                "umschalten",
                "umschauen",
                "umschichten",
                "umschlagen",
                "umschmeißen",
                "umschmeissen",
                "umschmelzen",
                "umschmieden",
                "umschminken",
                "umschnallen",
                "umschubsen",
                "umschulden",
                "umschulen",
                "umschütten",
                "umschwenken",
                "umsehen",
                "umsetzen",
                "umsiedeln",
                "umsinken",
                "umsortieren",
                "umspeichern",
                "umspringen",
                "umspritzen",
                "umspulen",
                "umstechen",
                "umstecken",
                "umsteigen",
                "umstellen",
                "umstempeln",
                "umsteuern",
                "umstilisieren",
                "umstimmen",
                "umstoßen",
                "umstossen",
                "umstrukturieren",
                "umstufen",
                "umstülpen",
                "umstürzen",
                "umtaufen",
                "umtauschen",
                "umteilen",
                "umtopfen",
                "umtragen",
                "umtreiben",
                "umtreten",
                "umtun",
                "umverteilen",
                "umwälzen",
                "umwandeln",
                "umwechseln",
                "umwehen",
                "umwenden",
                "umwerfen",
                "umwerten",
                "umwidmen",
                "umwühlen",
                "umzeichnen",
                "umziehen",
            ],
            "unter": [
                "unterbelegen",
                "unterbelichten",
                "unterbewerten",
                "unterbezahlen",
                "unterbringen",
                "unterbügeln",
                "unterbuttern",
                "unterducken",
                "untereinanderliegen",
                "untereinanderstehen",
                "unterfassen",
                "untergehen",
                "unterhaken",
                "unterheben",
                "unterjubeln",
                "unterkommen",
                "unterkriechen",
                "unterkriegen",
                "untermengen",
                "unterordnen",
                "unterpflügen",
                "unterrühren",
                "unterschieben",
                "unterschlupfen",
                "unterschlüpfen",
                "unterschnallen",
                "untersinken",
                "untertauchen",
                "untervermieten",
                "unterversichern",
                "unterversorgen",
                "unterwühlen",
                "uraufführen",
                "unterspannen",
            ],
        }

        prefixes = (
            "ge",
            "er",
            "be",
            "ent",
            "emp",
            "ver",
            "zer",
            "hinter",
            "miss",
            "ob",
        )

        if self.base_form.startswith(prefixes):
            return None

        prefixes = [
            "ab",
            "an",
            "auf",
            "aus",
            "bei",
            "ein",
            "mit",
            "nach",
            "weg",
            "zu",
            "her",
            "nach",
            "überein",
            "umher",
        ]
        for prefix in prefixes:
            if self.base_form.startswith(prefix):
                return prefix

        for prefix in splittable_words:
            if self.base_form.startswith(prefix):
                if self.base_form in splittable_words[prefix]:
                    return prefix

                return None

        # detect "adjective + verb" case
        i = 2  # skip the first 2 letters
        while i < len(self.base_form) - 2:  # skip the last 2 letters
            prefix = self.base_form[0:i]
            partial_word = self.base_form[i:]
            try:
                partial_word_result = GermanVerb.objects.get(base_form=partial_word)
            except GermanVerb.DoesNotExist:
                partial_word_result = None

            if partial_word_result is not None:
                try:
                    GermanAdjective.objects.get(base_form=prefix)
                    return prefix
                except GermanAdjective.DoesNotExist:
                    pass

            i += 1

        return None

    def fill_declensions_standard(self, base_form=None):
        if base_form is None:
            base_form = self.base_form
            splittable_prefix = self.german_verb_splittable()
            if splittable_prefix:
                base_form = self.base_form.removeprefix(splittable_prefix)
        else:
            splittable_prefix = self.base_form.removesuffix(base_form)

        adjective_postifx = " " + splittable_prefix if splittable_prefix else ""

        base_form = (
            base_form.removesuffix("en")
            if base_form.endswith("en")
            else base_form.removesuffix("n")
        )

        ending = "e" if base_form.endswith("t") else ""

        self.present_ich = base_form + "e" + adjective_postifx
        self.present_du = (
            base_form.replace("a", "ä") + ending + "st" + adjective_postifx
        )
        self.present_pronoun = (
            base_form.replace("a", "ä") + ending + "t" + adjective_postifx
        )
        self.past_tense_ich = base_form + ending + "te" + adjective_postifx
        self.past_participle = (
            self.base_form
            if self.base_form.startswith("ver")
            else (
                splittable_prefix + "ge" + base_form + ending + "t"
                if splittable_prefix
                else "ge" + base_form + ending + "t"
            )
        )
        self.conjunctive_ich = (
            base_form.replace("a", "ä") + ending + "te" + adjective_postifx
        )
        self.imperativ_singular = base_form + adjective_postifx + ending
        self.imperativ_plural = base_form + ending + "t" + adjective_postifx
        self.helping_verb = "haben/sein"
        self.infinitiv_zu = (
            splittable_prefix + "zu" + self.base_form.removeprefix(splittable_prefix)
            if splittable_prefix
            else "zu " + self.base_form
        )

        self.save()

        message = "Filled German verb with standard rules"
        return False, message

    def fill_declensions(self, _=None):
        soup = get_soup(self.base_form)
        if soup is None:
            message = "Unable to download German verb Wikitionary data"
            return True, message

        elements = soup.find_all("span", {"id": "Verb"})
        if len(elements) == 0:
            elements = soup.find_all("span", {"id": "Verb,_unregelmäßig"})

        if len(elements) == 0:
            message = "German verb data missing on Wikitionary"
            return True, message

        try:
            rows = elements[0].parent.find_next_sibling("table")
            if rows is None:
                message = "German verb data table missing on Wikitionary"
                return True, message

            verb_map = {
                "hilfe:präsens ich": "present_ich",
                "hilfe:präsens du": "present_du",
                "hilfe:präsens er, sie, es": "present_pronoun",
                "hilfe:präteritum ich": "past_tense_ich",
                "hilfe:konjunktiv ich": "conjunctive_ich",
                "hilfe:imperativ singular": "imperativ_singular",
                "hilfe:imperativ plural": "imperativ_plural",
                "hilfe:perfekt": [
                    "past_participle",
                    "helping_verb",
                ],
            }

            headline_name = ""
            for row in rows.find("tbody").find_all("tr"):
                columns = row.find_all("td")
                headlines = row.find_all("th")
                if len(headlines) and headlines[0].find("a"):
                    headline_name = headlines[0].find("a")["title"].strip().lower()

                if len(columns):
                    if headline_name in verb_map:
                        for i in range(len(verb_map[headline_name])):
                            element = columns[i].find("a")
                            text = element["title"] if element else ""
                            setattr(
                                self,
                                verb_map[headline_name][i],
                                text,
                            )
                    elif len(columns[0]):
                        column_name = columns[0].get_text().strip().lower()
                        verb_name = f"{headline_name} {column_name}"

                        if verb_name in verb_map:
                            element = columns[1].find("a")
                            text = element["title"] if element else ""
                            if (
                                text != ""
                                or getattr(
                                    self,
                                    verb_map[verb_name],
                                )
                                == None
                            ):
                                setattr(
                                    self,
                                    verb_map[verb_name],
                                    text,
                                )

            soup = get_soup(self.base_form, flexion=True)
            if soup is not None and soup.find("table"):
                element = soup.find("table")

                match = False
                for row in element.find("tbody").find_all("tr"):
                    if match:
                        columns = row.find_all("td")
                        if (
                            len(columns)
                            and columns[0].find("a")["title"] == "Hilfe:Aktiv"
                        ):
                            self.infinitiv_zu = columns[1].get_text()
                        break
                    else:
                        headlines = row.find_all("th")
                        if (
                            len(headlines)
                            and headlines[0].get_text().strip()
                            == "erweiterte Infinitive"
                        ):
                            match = True
        except AttributeError:
            message = "Unable to find German verb tag in Wikitionary data"
            return True, message
        except KeyError:
            message = "Unable to find German verb title in Wikitionary data"
            return True, message
        except Exception:
            message = "Unable to parse German verb Wikitionary data"
            return True, message

        self.save()

        message = "German verb declension data has been filled."
        return False, message

    base_form = models.CharField(max_length=255, unique=True)
    present_ich = models.CharField(
        max_length=255, null=True, blank=True, help_text="Present Ich"
    )
    present_du = models.CharField(
        max_length=255, null=True, blank=True, help_text="Present Du"
    )
    present_pronoun = models.CharField(
        max_length=255, null=True, blank=True, help_text="Present Er/Sie"
    )
    past_tense_ich = models.CharField(
        max_length=255, null=True, blank=True, help_text="Past Ich"
    )
    past_participle = models.CharField(
        max_length=255, null=True, blank=True, db_index=True, help_text="Past Perfekt"
    )
    conjunctive_ich = models.CharField(
        max_length=255, null=True, blank=True, help_text="Konjunktiv II Ich"
    )
    imperativ_singular = models.CharField(
        max_length=255, null=True, blank=True, help_text="Imperative Singular"
    )
    imperativ_plural = models.CharField(
        max_length=255, null=True, blank=True, help_text="Imperative Plural"
    )
    helping_verb = models.CharField(
        max_length=255, null=True, blank=True, help_text="Hilfsverb"
    )
    infinitiv_zu = models.CharField(
        max_length=255, null=True, blank=True, db_index=True, help_text="Infinitiv Zu"
    )


class GermanAdjective(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    def fill_declensions_standard(self, _=None):
        self.comparative = self.base_form + "er"
        self.superlative = (
            self.base_form + ("e" if self.base_form.endswith("t") else "") + "sten"
        )

        self.save()

        message = "Filled German adjective with standard rules"
        return False, message

    def fill_declensions(self, _=None):
        soup = get_soup(self.base_form)
        if soup is None:
            message = "Unable to download German adjective Wikitionary data"
            return True, message

        elements = soup.find_all("span", {"id": "Adjektiv"})
        if len(elements) == 0:
            message = "German adjective data missing on Wikitionary"
            return True, message

        try:
            rows = elements[0].parent.find_next_sibling("table")
            if rows is None:
                self.is_absolute = True
            else:
                adjective_map = [
                    "comparative",
                    "superlative",
                ]

                for row in rows.find("tbody").find_all("tr"):
                    columns = row.find_all("td")
                    if (
                        len(columns)
                        and len(columns[0].contents)
                        and columns[0].contents[0].strip() == self.base_form
                    ):
                        self.is_absolute = False
                        for i in range(len(columns[1:])):
                            element = columns[i + 1].find("a")
                            if element is None:
                                self.is_absolute = True
                            else:
                                setattr(
                                    self,
                                    adjective_map[i],
                                    columns[i + 1].find("a")["title"],
                                )

        except AttributeError:
            message = "Unable to find German adjective tag in Wikitionary data"
            return True, message
        except KeyError:
            message = "Unable to find German adjective title in Wikitionary data"
            return True, message
        except Exception:
            message = "Unable to parse German adjective Wikitionary data"
            return True, message

        if self.is_absolute:
            self.comparative = self.base_form
            self.superlative = self.base_form

        self.save()

        message = "German adjective declension data has been filled."
        return False, message

    def clean(self):
        super().clean()

        if self.is_absolute:
            self.comparative = self.base_form
            self.superlative = self.base_form

    base_form = models.CharField(max_length=255, unique=True)
    comparative = models.CharField(max_length=255, null=True, blank=True)
    superlative = models.CharField(max_length=255, null=True, blank=True)
    is_absolute = models.BooleanField(
        default=False, help_text="If adjective is in an absolute"
    )


class GermanNoun(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    def clean(self):
        super().clean()

        try:
            other_form = None
            if self.female_form:
                other_form = GermanNoun.objects.get(base_form=self.female_form)
            elif self.male_form:
                other_form = GermanNoun.objects.get(base_form=self.male_form)
        except GermanNoun.DoesNotExist:
            return

        # Add missing reference to other
        if other_form is None:
            try:
                other_form = GermanNoun.objects.get(female_form=self.base_form)
                if other_form is None:
                    other_form = GermanNoun.objects.get(male_form=self.base_form)

                if other_form is None:
                    return

                if other_form.female_form is not None:
                    self.male_form = other_form.base_form
                elif other_form.male_form is not None:
                    self.female_form = other_form.base_form
            except GermanNoun.DoesNotExist:
                return

        # check to see if collective_noun needs to be copied
        if self._state.adding:
            if self.collective_noun is None or len(self.collective_noun) == 0:
                self.collective_noun = other_form.collective_noun
            if self.collective_noun_2 is None or len(self.collective_noun_2) == 0:
                self.collective_noun_2 = other_form.collective_noun_2

            if other_form.female_form is not None:
                self.male_form = other_form.base_form
            elif other_form.male_form is not None:
                self.female_form = other_form.base_form
        # update collective_noun on the other form
        else:
            other_form.collective_noun = self.collective_noun
            other_form.collective_noun_2 = self.collective_noun_2
            if self.female_form is not None:
                other_form.male_form = self.base_form
            elif self.male_form is not None:
                other_form.female_form = self.base_form
            other_form.save()

    def get_variant(self, base_form, female_form=True):
        soup = get_soup(self.base_form)
        if soup is None:
            return None

        title = (
            "Weibliche Varianten des Wortes"
            if female_form
            else "Männliche Wortformen Varianten des Wortes"
        )
        elements = soup.find_all("p", {"title": title})
        if len(elements) == 0:
            return None

        try:
            variant = (
                elements[0]
                .find_next("dl")
                .find("dd")
                .find("a", attrs={"title": True})["title"]
            ).removesuffix(" (Seite nicht vorhanden)")
        except Exception:
            return None

        return variant if len(variant) else None

    def fill_declensions_standard(self, _=None):
        endings = ["s", "n"]
        is_feminine = self.base_form.endswith("in")
        is_leute = False
        if is_feminine:
            self.gender_1 = GenderTypeEnum.FEMININE
            self.male_form = self.base_form.removesuffix("in")
        else:
            if self.base_form.lower().endswith("frau"):
                self.gender_1 = GenderTypeEnum.FEMININE
                suffix = "mann" if self.base_form.endswith("frau") else "Mann"
                self.male_form = self.base_form.removesuffix("frau") + suffix
                is_leute = True
            elif self.base_form.lower().endswith("mann"):
                self.gender_1 = GenderTypeEnum.MASCULINE
                suffix = "frau" if self.base_form.endswith("mann") else "Frau"
                self.male_form = self.base_form.removesuffix("mann") + suffix
                is_leute = True

        if self.female_form is None or len(self.female_form) == 0:
            self.female_form = self.get_variant(self.base_form)

        if self.male_form is None or len(self.male_form) == 0:
            self.male_form = self.get_variant(self.base_form, False)

        if not self.plural_only:
            self.sg_nom = self.base_form
            if is_feminine:
                self.sg_dat = self.base_form
            else:
                ending = "e" if self.base_form[-1] in endings else ""
                self.sg_dat = self.base_form + ending + "s"
            self.sg_gen = self.base_form
            self.sg_acc = self.base_form

        if not self.singular_only:
            if is_feminine:
                self.pl_nom = self.base_form + "nen"
                self.pl_gen = self.base_form + "nen"
                self.pl_dat = self.base_form + "nen"
                self.pl_acc = self.base_form + "nen"
            else:
                if is_leute:
                    base_form = self.base_form[0:-4] + (
                        "leute" if self.base_form[-4:-3].islower() else "Leute"
                    )
                    ending = ""
                else:
                    ending = ""
                    if self.base_form[-1] in endings:
                        ending = "" if self.base_form.endswith("e") else "e"
                        endings += "r"

                    base_form = self.base_form.replace("a", "ä").replace("A", "Ä")

                self.pl_nom = base_form + ending
                self.pl_gen = base_form + ending
                self.pl_dat = base_form + ending + "n"
                self.pl_acc = base_form + ending

        self.save()

        message = "Filled German noun with standard rules"
        return False, message

    def modify_noun(self, noun, noun_prefix, noun_superfix, lower_case):
        if noun is None or len(noun) == 0:
            return None

        if noun_superfix:
            return noun.replace(noun_superfix, "").capitalize()

        if lower_case:
            noun = noun.lower()

        return noun_prefix + noun

    def fill_declensions(self, base_form=None):
        noun_prefix = None
        noun_superfix = None
        lower_case = True
        if base_form is None:
            base_form = self.base_form
        else:
            if base_form.lower() in self.base_form:
                noun_prefix = self.base_form.replace(base_form.lower(), "")
            elif base_form in self.base_form:
                lower_case = False
                noun_prefix = self.base_form.replace(base_form, "")
            elif self.base_form.lower() in base_form:
                noun_superfix = base_form.replace(self.base_form.lower(), "")
            elif self.base_form in base_form:
                lower_case = False
                noun_superfix = base_form.replace(self.base_form, "")
            else:
                message = f"Supplied base form {base_form} for German noun gender not contained in {self.base_form} (or vice-versa)"
                return True, message

            try:
                noun = GermanNoun.objects.get(base_form=base_form)

                self.female_form = self.modify_noun(
                    noun.female_form,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.male_form = self.modify_noun(
                    noun.male_form,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.gender_1 = noun.gender_1
                self.gender_2 = noun.gender_2
                self.singular_only = noun.singular_only
                self.plural_only = noun.plural_only
                self.sg_nom = self.modify_noun(
                    noun.sg_nom,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.sg_dat = self.modify_noun(
                    noun.sg_dat,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.sg_dat_2 = self.modify_noun(
                    noun.sg_dat_2,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.sg_gen = self.modify_noun(
                    noun.sg_gen,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.sg_gen_2 = self.modify_noun(
                    noun.sg_gen_2,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.sg_acc = self.modify_noun(
                    noun.sg_acc,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.pl_nom = self.modify_noun(
                    noun.pl_nom,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.pl_gen = self.modify_noun(
                    self.pl_gen,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.pl_dat = self.modify_noun(
                    noun.pl_dat,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )
                self.pl_acc = self.modify_noun(
                    noun.pl_acc,
                    noun_prefix,
                    noun_superfix,
                    lower_case,
                )

                self.save()

                message = f"German noun declension data has been filled via '{noun.base_form}' declension data."
                return False, message
            except GermanNoun.DoesNotExist:
                pass

        soup = get_soup(base_form, "verbformen")
        if soup is None:
            message = "Unable to download German noun gender variant verbformen data"
            return self.fill_declensions_wikitionary(message)

        element = soup.find("span", {"title": "Substantiv"})
        if element is None:
            message = "Unable to find German noun data on verbformen"
            return self.fill_declensions_wikitionary(message)

        gender_map = {
            "feminin": GenderTypeEnum.FEMININE,
            "maskulin": GenderTypeEnum.MASCULINE,
            "neutral": GenderTypeEnum.NEUTER,
        }

        i = 1
        for t in soup.select("span[title*=Genus]"):
            title = t["title"].split()
            if len(title) == 2 and title[1] in gender_map:
                setattr(self, "gender_" + str(i), gender_map[title[1]])
                i += 1

        elements = soup.find_all("div", {"class": "vTbl"})
        if len(elements) == 0:
            message = "Unable to find table for German noun gender verbformen data"
            return self.fill_declensions_wikitionary(message)

        heading_map = {
            "Nom.": "nom",
            "Dat.": "dat",
            "Gen.": "gen",
            "Akk.": "acc",
        }

        has_singular = False
        has_plural = False
        for element in elements:
            table = element.find("table")
            rows = table.find_all("tr")

            if len(rows):
                is_singular = element.find("h2").get_text() == "Singular"

                prefix = "sg_" if is_singular else "pl_"
                for row in rows:
                    heading = row.find("th").get_text()
                    if heading in heading_map:
                        columns = row.find_all("td")
                        if len(columns) == 2 and columns[1].get_text():
                            if is_singular:
                                has_singular = True
                            else:
                                has_plural = True

                            variations = columns[1].get_text().split("/")
                            if noun_prefix is not None:
                                for i in range(len(variations)):
                                    variations[i] = strip_non_alpha(variations[i])
                                    variations[i] = self.modify_noun(
                                        variations[i],
                                        noun_prefix,
                                        noun_superfix,
                                        lower_case,
                                    )

                            elif noun_superfix is not None:
                                for i in range(len(variations)):
                                    variations[i] = self.modify_noun(
                                        strip_non_alpha(variations[i]),
                                        noun_prefix,
                                        noun_superfix,
                                        lower_case,
                                    )

                            setattr(
                                self,
                                prefix + heading_map[heading],
                                strip_non_alpha(variations[0]),
                            )

                            if (
                                len(variations) > 1
                                and is_singular
                                and heading_map[heading] in ["dat", "gen"]
                            ):
                                setattr(
                                    self,
                                    prefix + heading_map[heading] + "_2",
                                    strip_non_alpha(variations[1]),
                                )

        if has_singular and has_plural:
            self.singular_only = False
            self.plural_only = False
        elif has_singular:
            self.singular_only = True
            self.plural_only = False
        elif has_plural:
            self.plural_only = True
            self.singular_only = False

        self.save()

        message = "German noun declension data has been filled via verbformen."
        return False, message

    def fill_declensions_wikitionary(self, message):
        soup = get_soup(self.base_form)
        if soup is None:
            message += ". Unable to download German noun Wikitionary data"
            return True, message

        gender_map = {
            "": None,
            "f": GenderTypeEnum.FEMININE,
            "m": GenderTypeEnum.MASCULINE,
            "n": GenderTypeEnum.NEUTER,
        }

        elements = soup.find_all("a", {"href": "/wiki/Hilfe:Wortart#Substantiv"})
        if len(elements) == 0:
            nouns = Nouns()
            result = nouns[self.base_form]
            if len(result) == 0 or len(result[0]["flexion"]) == 0:
                if "-" in self.base_form:
                    words = self.base_form.split("-")
                    word = words[-1]
                    prefix = "-".join(words[0:-1]) + "-"
                    lower = False
                else:
                    words = nouns.parse_compound(self.base_form)
                    if len(words) < 1 or not self.base_form.endswith(words[-1].lower()):
                        message += ". Could not split German noun"
                        return True, message

                    word = words[-1]
                    prefix = self.base_form.removesuffix(word.lower())
                    lower = True

                result = nouns[word]
                if len(result) == 0:
                    message += ". Could not determine German noun flexion"
                    return True, message

                for i in range(len(result)):
                    lemma = result[i]["lemma"].lower() if lower else result[i]["lemma"]
                    result[i]["lemma"] = prefix + lemma
                    for flexion in result[i]["flexion"]:
                        flexion_expanded = (
                            result[i]["flexion"][flexion].lower()
                            if lower
                            else result[i]["flexion"][flexion]
                        )
                        result[i]["flexion"][flexion] = prefix + flexion_expanded

            result = result[0]

            singular = False
            singular_map = {
                "nominativ singular": "sg_nom",
                "dativ singular": "sg_dat",
                "dativ singular*": "sg_dat_2",
                "genitiv singular": "sg_gen",
                "genitiv singular*": "sg_gen_2",
                "akkusativ singular": "sg_acc",
            }

            plural = False
            plural_map = {
                "nominativ plural": "pl_nom",
                "dativ plural": "pl_dat",
                "genitiv plural": "pl_gen",
                "akkusativ plural": "pl_acc",
            }

            for flexion in result["flexion"]:
                # TODO handle variations (dativ/genetiv) and stark/schwach/gemischt
                key = flexion.removesuffix(" 1").removesuffix(" stark")
                if key in singular_map:
                    setattr(self, singular_map[key], result["flexion"][flexion])
                    singular = True
                elif key in plural_map:
                    setattr(self, plural_map[key], result["flexion"][flexion])
                    plural = True

            if (
                self.sg_gen is not None
                and self.sg_gen.endswith("es")
                and self.sg_gen_2 is not None
                and not self.sg_gen_2.endswith("es")
            ):
                sg_gen = self.sg_gen
                self.sg_gen = self.sg_gen_2
                self.sg_gen_2 = sg_gen

            if self.sg_dat == self.sg_dat_2:
                self.sg_dat_2 = None

            if self.sg_gen == self.sg_gen_2:
                self.sg_gen_2 = None

            if not singular and not plural:
                message = "Could not find German noun flexion"
                return True, message

            self.singular_only = bool(singular and not plural)
            self.plural_only = bool(plural and not singular)

            if "genus" not in result and "genus 1" not in result:
                message = "German noun genus could not be determined"
                return True, message

            self.gender_1 = (
                gender_map[result["genus"]]
                if "genus" in result
                else gender_map[result["genus 1"]]
            )

            self.gender_2 = (
                gender_map[result["genus 2"]] if "genus 2" in result else None
            )
        else:
            element = elements[0].parent
            genders = (
                element["id"].removeprefix("Substantiv,").replace("_", "").split(",")
            )
            self.gender_1 = gender_map[genders[0]]
            if len(genders) > 1 and genders[1] in gender_map:
                self.gender_2 = gender_map[genders[1]]

            try:
                rows = element.parent.find_next_sibling("table")
                if rows is None:
                    message += ". German noun data table missing on Wikitionary"
                    return True, message

                noun_map = {
                    "hilfe:nominativ": "nom",
                    "hilfe:genitiv": "gen",
                    "hilfe:dativ": "dat",
                    "hilfe:akkusativ": "acc",
                }

                headline_name = ""
                pluralization_map = []
                for row in rows.find("tbody").find_all("tr"):
                    headlines = row.find_all("th")
                    if len(headlines) and headlines[0].find("a"):
                        headline_name = headlines[0].find("a")["title"].strip().lower()
                    else:
                        pluralization_map = []
                        for i in range(len(headlines[1:])):
                            title = headlines[i + 1].get_text().strip()
                            value = "sg_" if title.startswith("Singular") else "pl_"
                            value += "PLACEHOLDER"
                            if title.endswith(" 2"):
                                value += "_2"

                            pluralization_map.append(value)

                        continue

                    columns = row.find_all("td")

                    if (
                        len(columns)
                        and len(pluralization_map)
                        and headline_name in noun_map
                    ):
                        for i in range(len(columns)):
                            if pluralization_map[i].endswith("_2") and (
                                "plural" in pluralization_map[i]
                                or noun_map[headline_name] not in ["dat", "gen"]
                            ):
                                continue

                            attribute_name = pluralization_map[i].replace(
                                "PLACEHOLDER", noun_map[headline_name]
                            )

                            for k in range(len(columns[i].contents)):
                                field = columns[i].contents[k]
                                text = (
                                    field.get_text()
                                    .strip()
                                    .removeprefix("die ")
                                    .removeprefix("das ")
                                    .removeprefix("der ")
                                    .removeprefix("den ")
                                    .removeprefix("dem ")
                                    .removeprefix("des ")
                                )
                                if len(text) and text[0].isupper():
                                    if k > 1:
                                        attribute_name += "_2"

                                    setattr(
                                        self,
                                        attribute_name,
                                        text,
                                    )
            except AttributeError:
                message += ". Unable to find German noun tag in Wikitionary data"
                return True, message
            except KeyError:
                message += ". Unable to find German noun title in Wikitionary data"
                return True, message
            except Exception:
                message += ". Unable to parse German noun Wikitionary data"
                return True, message

        if self.female_form is None or len(self.female_form) == 0:
            self.female_form = self.get_variant(self.base_form)

        if self.male_form is None or len(self.male_form) == 0:
            self.male_form = self.get_variant(self.base_form, False)

        self.save()

        message = "German noun declension data has been filled via Wikitionary."
        return False, message

    base_form = models.CharField(max_length=255, unique=True)
    female_form = models.CharField(max_length=255, null=True, blank=True)
    male_form = models.CharField(max_length=255, null=True, blank=True)
    gender_1 = EnumField(GenderTypeEnum, null=True, blank=True)
    gender_2 = EnumField(GenderTypeEnum, null=True, blank=True)
    singular_only = models.BooleanField(default=False)
    plural_only = models.BooleanField(default=False)
    sg_nom = models.CharField(max_length=255, null=True, blank=True)
    sg_dat = models.CharField(max_length=255, null=True, blank=True)
    sg_dat_2 = models.CharField(max_length=255, null=True, blank=True)
    sg_gen = models.CharField(max_length=255, null=True, blank=True)
    sg_gen_2 = models.CharField(max_length=255, null=True, blank=True)
    sg_acc = models.CharField(max_length=255, null=True, blank=True)
    pl_nom = models.CharField(max_length=255, null=True, blank=True)
    pl_nom_2 = models.CharField(max_length=255, null=True, blank=True)
    pl_gen = models.CharField(max_length=255, null=True, blank=True)
    pl_dat = models.CharField(max_length=255, null=True, blank=True)
    pl_acc = models.CharField(max_length=255, null=True, blank=True)
    collective_noun = models.CharField(max_length=255, null=True, blank=True)
    collective_noun_2 = models.CharField(max_length=255, null=True, blank=True)
