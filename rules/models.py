from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.conf import settings

from django_enum import EnumField
from ordered_model.models import OrderedModel
from taggit.managers import TaggableManager
from computedfields.models import ComputedFieldsModel, computed

import emoji

import requests
from requests.auth import HTTPBasicAuth


class LanguageEnum(models.TextChoices):
    EN = "en", "English"
    DE = "de", "German"


class AlternativePluralizationEnum(models.TextChoices):
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


class Source(BaseTimestampedModel, BaseCreatedByModel):
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
    @property
    def language(self):
        if self.rule:
            return self.rule.language

        return self.language

    def get_json(self, path):
        url = settings.NLP_API + path

        auth = (
            HTTPBasicAuth(settings.NLP_API_USER, settings.NLP_API_PASSWORD)
            if settings.NLP_API_USER is not None
            else None
        )

        r = requests.get(url, auth=auth)

        if r.status_code != 200:
            body = r.json()
            error = body["detail"] if "detail" in body else r.text
            raise ValidationError(path + ": " + error)

        return r.json()

    def tokenize(self):
        path = f"/tokenize?lang={requests.utils.quote(self.language)}&text={requests.utils.quote(self.lemma)}"
        return self.get_json(path)

    def parse_word_type(self):
        if self.word_types is None or len(self.word_types) == 0:
            return None

        path = f"/parse-word-type?lang={requests.utils.quote(self.language)}&text={requests.utils.quote(self.lemma)}&word_types={requests.utils.quote(self.word_types)}"
        return self.get_json(path)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        try:
            self.tokenized = self.tokenize()
        except ValidationError as exception:
            errors["lemma"] = "Lemma could not be tokenized: " + exception.message

        try:
            self.parsed_word_type = self.parse_word_type()
        except ValidationError as exception:
            errors["word_types"] = "Word_types validation failed: " + exception.message

        if len(errors):
            raise ValidationError(errors)

    class Meta:
        abstract = True

    tokenized = None
    parsed_word_type = None

    lemma = models.CharField(
        max_length=255,
        help_text="Lemma is one or multiple words (tokens) either in lemmatized for or not (depending on the word_types)",
    )

    @computed(models.JSONField(default=dict))
    def lemma_json(self):
        return self.tokenized

    word_types = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="'|' separated list of word types (s, a, adv, v, conj, emoji) and optional modifiers: '=' case sensitive unlemmatized, '~' case insensitive unlemmatize, '-' case sensitive lemmatized",
    )

    @computed(models.JSONField(default=dict))
    def word_types_json(self):
        return [] if self.parsed_word_type is None else self.parsed_word_type

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
    OrderedModel, ComputedFieldsModel, BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel
):
    class Meta(OrderedModel.Meta):
        unique_together = (("parent_name", "is_advanced"),)

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

    @computed(models.BooleanField(null=True, blank=True))
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
        unique_together = (("language", "lemma", "word_types"),)
        indexes = [
            models.Index(
                fields=[
                    "first_token",
                    "first_is_word_type_lemmatize",
                    "first_is_word_type_lower_case",
                    "first_word_type",
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

        if self.label_type != "default" and self.label != "":
            errors["label_type"] = errors[
                "label"
            ] = "Change label type to 'default' or change label to an empty string"

        if len(errors):
            raise ValidationError(errors)

    def __str__(self):
        return self.lemma[0:50] + " (" + self.language + ")"

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)
    tags = TaggableManager(blank=True)

    text_id = models.CharField(
        max_length=255,
        help_text="String used to identify the rule, f.e. in the top words of the analytics",
    )

    type = EnumField(
        RuleTypeEnum,
        default=RuleTypeEnum.DEFAULT,
        help_text="Should the rule check on part of the lemma (only 'default' allows multiple token lemma).",
    )

    label_type = EnumField(
        RuleLabelEnum,
        default=RuleLabelEnum.DEFAULT,
        help_text="Quick selections for custom labels (only change from 'default' if label is empty).",
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

    @computed(models.CharField(max_length=255, null=True, blank=True))
    def first_token(self):
        if self.lemma_json is None or len(self.lemma_json) == 0:
            return None

        return self.lemma_json[0]

    @computed(models.CharField(max_length=255, null=True, blank=True))
    def first_word_type(self):
        if self.parsed_word_type is None or len(self.parsed_word_type) == 0:
            return None

        return self.parsed_word_type[0]["word_types"]

    @computed(models.BooleanField(null=True, blank=True))
    def first_is_word_type_lemmatize(self):
        if self.parsed_word_type is None or len(self.parsed_word_type) == 0:
            return None

        return self.parsed_word_type[0]["lemmatize"]

    @computed(models.BooleanField(null=True, blank=True))
    def first_is_word_type_lower_case(self):
        if self.parsed_word_type is None or len(self.parsed_word_type) == 0:
            return None

        return self.parsed_word_type[0]["lower_case"]

    @computed(models.JSONField(default=dict))
    def diversity_dimension_json(self):
        diversity_dimensions = []
        for diversity_dimension in self.diversity_dimensions.all():
            diversity_dimensions.append(diversity_dimension.name)

        return diversity_dimensions


class RuleDiversityDimension(OrderedModel, BaseTimestampedModel):
    class Meta:
        unique_together = (("rule", "diversity_dimension"),)
        ordering = ("order",)

    def __str__(self):
        return str(self.diversity_dimension)

    order_with_respect_to = "rule"

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)
    diversity_dimension = models.ForeignKey(
        DiversityDimension, on_delete=models.CASCADE
    )


class Alternative(
    OrderedModel,
    BaseLemmaModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    class Meta:
        ordering = ("order",)

    def __str__(self):
        return self.lemma[0:50]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        if self.is_remove:
            self.lemma = "-"
            self.word_types = ""

    order_with_respect_to = "rule"

    rule = models.ForeignKey(
        Rule, related_name="alternatives", on_delete=models.CASCADE
    )

    type = EnumField(AlternativeTypeEnum, default=AlternativeTypeEnum.DEFAULT)
    pluralization = EnumField(
        AlternativePluralizationEnum,
        default=AlternativePluralizationEnum.DEFAULT,
        help_text="Show alternative in case rule triggered on",
        AlternativePluralizationEnum, default=AlternativePluralizationEnum.DEFAULT
    )
    is_inspiration = models.BooleanField(
        default=False,
        help_text="Alternative will be marked as inspiration, hidden if user has inspiration disabled. Also never adjusted for grammatical correctness",
    )
    is_advanced = models.BooleanField(
        default=True,
        help_text="Only show if user has diversity dimension enabled at advanced level.",
    )

    @computed(models.BooleanField(default=False))
    def is_placeholder(self):
        return "((" in self.lemma and "))" in self.lemma

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

    is_false_positive = models.BooleanField(default=False)
    is_training_data = models.BooleanField(default=False)

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


class Verb(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    class Meta:
        unique_together = (("language", "base_form"),)

    base_form = models.CharField(max_length=255, unique=True)
    language = EnumField(LanguageEnum, default=LanguageEnum.DE)


class Adjective(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    class Meta:
        unique_together = (("language", "base_form"),)

    base_form = models.CharField(max_length=255, unique=True)
    language = EnumField(LanguageEnum, default=LanguageEnum.DE)


class Noun(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.base_form

    class Meta:
        unique_together = (("language", "base_form"),)

    base_form = models.CharField(max_length=255, unique=True)
    language = EnumField(LanguageEnum, default=LanguageEnum.DE)
