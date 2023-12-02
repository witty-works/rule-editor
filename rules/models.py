from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.conf import settings

from django_enum import EnumField
from taggit.managers import TaggableManager
from computedfields.models import ComputedFieldsModel, computed

import emoji

import requests
from requests.auth import HTTPBasicAuth


def fetch_json(path, data=None):
    url = settings.NLP_API + path

    auth = (
        HTTPBasicAuth(settings.NLP_API_USER, settings.NLP_API_PASSWORD)
        if settings.NLP_API_USER is not None
        else None
    )

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


class LanguageEnum(models.TextChoices):
    EN = "en", "English"
    DE = "de", "German"


class GenderTypeEnum(models.TextChoices):
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
            return ["-"], ["-"]

        path = f"/debug/spacy?lang={requests.utils.quote(self.language)}&text={requests.utils.quote(self.lemma)}"
        result = fetch_json(path)
        result.pop(0)
        tokens = []
        lemmas = []
        for token in result:
            tokens.append(token["text"])
            lemmas.append(token["lemma"])

        return tokens, lemmas

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
            self.tokenized, lemmas = self.tokenize()
        except ValidationError as exception:
            errors["lemma"] = "Lemma could not be tokenized: " + exception.message

        try:
            self.parsed_word_types = self.parse_word_types()
        except ValidationError as exception:
            errors["word_types"] = "Word_types validation failed: " + exception.message

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
        help_text="'|' separated list of word types (n, a, adv, v, conj, emoji) and optional modifiers: '=' case sensitive unlemmatized, '~' case insensitive unlemmatize, '-' case sensitive lemmatized",
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

    @computed(
        models.BooleanField(null=True, blank=True),
        depends=[
            ("self", ["name"]),
        ],
    )
    def is_advanced(self):
        self.is_advanced = self.name.endswith("_advanced")


class Rule(
    BaseLemmaModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    class Meta:
        unique_together = (("language", "lemma", "word_types", "type", "pluralization"),)
        indexes = [
            models.Index(
                fields=[
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

        if self.url is not None:
            validator = URLValidator()
            try:
                validator(self.url)
            except ValidationError as exception:
                errors["url"] = (
                    "URL must either be empty or a valid URL: " + exception.message
                )

        if self.type != "default":
            if self.tokenized is not None and len(self.tokenized) > 1:
                errors["type"] = "Rules with a non default type can only have one token"

        if len(errors):
            raise ValidationError(errors)

    def __str__(self):
        return self.lemma[0:50] + " (" + self.language + ")"

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)
    tags = TaggableManager(blank=True)

    pattern = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional pattern to define word types before and after the lemma. Syntax 'l' for the lemma. '*' means zero or many, '+' means once or many.",
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

    sanctions = models.ManyToManyField(Source, blank=True, related_name='rule_sanctions')

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
            ("diversity_dimensions", ["name"]),
            ("rulediversitydimension", ["diversity_dimension"]),
        ],
        prefetch_related=["diversity_dimensions"],
    )
    def diversity_dimension_json(self):
        diversity_dimensions = []
        if self.pk:
            for diversity_dimension in self.diversity_dimensions.all():
                diversity_dimensions.append(diversity_dimension.name)

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
    sanctions = models.ManyToManyField(Source, blank=True, related_name='alternative_sanctions')

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
    BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel, BaseSourcedModel
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
    is_on_website = models.BooleanField(
        default=False, help_text="If sentences is an example on the website"
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

    base_form = models.CharField(max_length=255, unique=True)
    past_tense = models.CharField(max_length=255, null=True, blank=True)
    past_participle = models.CharField(max_length=255, null=True, blank=True)
    present_participle = models.CharField(max_length=255, null=True, blank=True)
    third_person_singular = models.CharField(max_length=255, null=True, blank=True)


class EnglishAdjective(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

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

    base_form = models.CharField(max_length=255, unique=True)
    plural = models.CharField(max_length=255, null=True, blank=True)


class GermanVerb(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    base_form = models.CharField(max_length=255, unique=True)
    present_ich = models.CharField(max_length=255, null=True, blank=True)
    present_du = models.CharField(max_length=255, null=True, blank=True)
    present_pronoun = models.CharField(max_length=255, null=True, blank=True)
    past_tense_ich = models.CharField(max_length=255, null=True, blank=True)
    past_participle = models.CharField(
        max_length=255, null=True, blank=True, db_index=True
    )
    conjunctive_ich = models.CharField(max_length=255, null=True, blank=True)
    imperativ_singular = models.CharField(max_length=255, null=True, blank=True)
    imperativ_plural = models.CharField(max_length=255, null=True, blank=True)
    helping_verb = models.CharField(max_length=255, null=True, blank=True)
    infinitiv_zu = models.CharField(
        max_length=255, null=True, blank=True, db_index=True
    )


class GermanAdjective(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

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
    pl_gen = models.CharField(max_length=255, null=True, blank=True)
    pl_gen_2 = models.CharField(max_length=255, null=True, blank=True)
    pl_dat = models.CharField(max_length=255, null=True, blank=True)
    pl_dat_2 = models.CharField(max_length=255, null=True, blank=True)
    pl_acc = models.CharField(max_length=255, null=True, blank=True)
