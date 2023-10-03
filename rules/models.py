from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.conf import settings

from django_enum import EnumField
from ordered_model.models import OrderedModel
from taggit.managers import TaggableManager

import emoji

import requests
from requests.auth import HTTPBasicAuth


class LanguageEnum(models.TextChoices):
    EN = "en", "English"
    DE = "de", "German"


class ContentEnum(models.TextChoices):
    BASIC = "basic"
    ADVANCED = "advanced"
    VIDEO = "video"


class ProficiencyLevelEnum(models.TextChoices):
    HATE = "hate"
    BASIC = "basic"
    ADVANCED = "advanced"


class AlternativePLuralizationEnum(models.TextChoices):
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
    comment = models.TextField(null=True, blank=True)

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

    name = models.CharField(max_length=255, unique=True)
    url = models.CharField(max_length=255, null=True, blank=True)
    reference = models.TextField(null=True, blank=True)
    tags = TaggableManager(blank=True)


class BaseSourcedModel(BaseModel):
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True


class BaseLemmaModel(BaseModel):
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
            raise ValidationError(error)

        return r.json()

    def tokenize(self):
        path = f"/tokenize?lang={self.language}&text={self.lemma}"
        return self.get_json(path)

    def parse_word_type(self):
        path = f"/parse-word-type?lang={self.language}&text={self.lemma}&word_types={self.word_types}"
        return self.get_json(path)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        try:
            tokens = self.tokenize()
        except ValidationError as exception:
            errors["lemma"] = "Lemma could not be tokenized: " + exception.message

        try:
            self.parse_word_type()
        except ValidationError as exception:
            errors["word_types"] = "Word_types validation failed: " + exception.message

        if len(errors):
            raise ValidationError(errors)

        self.lemma_json = tokens
        self.word_types_json = self.word_types.split("|")

    class Meta:
        abstract = True

    lemma = models.CharField(max_length=255)
    lemma_json = models.JSONField(default=dict)
    word_types = models.CharField(max_length=255)
    word_types_json = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    label = models.TextField(null=True, blank=True)


class Category(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    name = models.CharField(max_length=255, unique=True)


class DiversityDimension(
    OrderedModel, BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel
):
    def __str__(self):
        return self.name

    name = models.CharField(max_length=255, unique=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    is_advanced = models.BooleanField(default=True)


class Rule(
    BaseLemmaModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    class Meta:
        unique_together = (("language", "lemma", "word_types"),)

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
            try:
                tokens = self.tokenize()
            except ValidationError as exception:
                errors["lemma"] = "Lemma could not be tokenized: " + exception.message

            if len(tokens) > 1:
                errors["type"] = "Rules with a non default type can only have one token"

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

    is_context_aware = models.BooleanField(
        default=False,
        help_text="Uses custom machine learning model to determine if to highlight in the given context.",
    )
    is_marked_for_review = models.BooleanField(default=False)

    diversity_dimensions = models.ManyToManyField(
        DiversityDimension, through="RuleDiversityDimension"
    )

    ownedby = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="owner"
    )

    explanation = models.CharField(max_length=255, null=True, blank=True)
    emoji = models.CharField(max_length=5, null=True, blank=True)
    url = models.CharField(max_length=255, null=True, blank=True)


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

    order_with_respect_to = "rule"

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    type = EnumField(AlternativeTypeEnum, default=AlternativeTypeEnum.DEFAULT)
    pluralization = EnumField(
        AlternativePLuralizationEnum, default=AlternativePLuralizationEnum.DEFAULT
    )
    is_inspiration = models.BooleanField(default=False)
    is_advanced = models.BooleanField(default=True)

    tags = TaggableManager(blank=True)


class TrainingSentence(
    BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel, BaseSourcedModel
):
    def __str__(self):
        return self.text

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    text = models.TextField(null=True, blank=True)

    is_false_positive = models.BooleanField(default=False)
    is_training_data = models.BooleanField(default=False)

    tags = TaggableManager(blank=True)


class FalsePositive(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.false_positive

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    false_positive = models.CharField(max_length=255, unique=True)


class Lemmatization(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.text

    class Meta:
        unique_together = (("language", "text"),)

    text = models.CharField(max_length=255)
    language = EnumField(LanguageEnum, default=LanguageEnum.EN)
    lemma = models.CharField(max_length=255)


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
