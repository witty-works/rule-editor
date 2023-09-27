from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings

from django_enum import EnumField
from ordered_model.models import OrderedModel
from hidefield.fields import HideField

import requests
from requests.auth import HTTPBasicAuth


class HideTextField(HideField, models.TextField):
    pass


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
    comment = HideTextField(null=True, blank=True, hide="no-data")

    class Meta:
        abstract = True


class Source(BaseTimestampedModel, BaseCreatedByModel):
    name = models.CharField(max_length=255, unique=True)
    url = models.TextField(null=True, blank=True)
    reference = HideTextField(null=True, blank=True)

    def __str__(self):
        return self.name


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

    def get_url(self, path):
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
            raise ValidationError({"word_types": error})

        return r

    def tokenize(self):
        path = f"/tokenize?lang={self.language}&text={self.lemma}"
        r = self.get_url(path)

        return r.json()

    def validate_word_type(self):
        path = f"/validate-word-type?lang={self.language}&text={self.lemma}&word_types={self.word_types}"
        self.get_url(path)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        self.validate_word_type()

        self.lemma_json = self.tokenize()
        self.word_types_json = self.word_types.split("|")

    class Meta:
        abstract = True

    lemma = models.CharField(max_length=255)
    lemma_json = models.JSONField(default=dict)
    word_types = models.CharField(max_length=255)
    word_types_json = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    label = HideTextField(null=True, blank=True, hide="no-data")


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


class AlternativeEnum(models.TextChoices):
    DEFAULT = "default"
    PERSON_FIRST = "person_first"
    IDENTITY_FIRST = "identity_first"


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
    category = models.ForeignKey(Category, on_delete=models.CASCADE)


class Rule(
    BaseLemmaModel,
    BaseTimestampedModel,
    BaseCreatedByModel,
    BaseCommentableModel,
    BaseSourcedModel,
):
    class Meta:
        unique_together = (("language", "lemma", "word_types", "lemma"),)

    def __str__(self):
        return self.lemma[0:50] + " (" + self.language + ")"

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)

    is_context_aware = models.BooleanField(default=False)
    is_prefix = models.BooleanField(default=False)
    is_marked_for_review = models.BooleanField(default=False)

    diversity_dimensions = models.ManyToManyField(
        DiversityDimension, through="RuleDiversityDimension"
    )

    ownedby = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="owner"
    )


class RuleDiversityDimension(OrderedModel, BaseTimestampedModel):
    class Meta:
        unique_together = (("rule", "diversity_dimension"),)
        ordering = ("order",)

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

    type = EnumField(AlternativeEnum, default=AlternativeEnum.DEFAULT)
    is_singular = models.BooleanField(default=True)
    is_inspiration = models.BooleanField(default=False)


class TrainingSentence(
    BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel, BaseSourcedModel
):
    def __str__(self):
        return self.text

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    text = models.TextField(null=True, blank=True)

    is_false_positive = models.BooleanField(default=False)
    is_training_data = models.BooleanField(default=False)


class FalsePositive(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    def __str__(self):
        return self.name

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    name = models.CharField(max_length=255, unique=True)
