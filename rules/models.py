from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

from django_enum import EnumField
from ordered_model.models import OrderedModel

class AutoDateTimeField(models.DateTimeField):
    def pre_save(self, model_instance, add):
        return timezone.now()

class BaseModel(models.Model):
    id = models.AutoField(
    	primary_key=True,
        unique=True,
        editable=False
    )

    class Meta:
    	abstract = True

class BaseTimestampedModel(models.Model):
    created_at = models.DateField(default=timezone.now, editable=False)
    updated_at = AutoDateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True

class TimestampedModelMixin(BaseTimestampedModel):
    class Meta:
        abstract = True

class BaseCreatedByModel(models.Model):
    createdby = models.ForeignKey(User, null=True, editable=False, on_delete=models.SET_NULL)

    class Meta:
        abstract = True

class CreatedbyModelMixin(BaseTimestampedModel, BaseCreatedByModel):
    class Meta:
        abstract = True

class BaseCommentableModel(models.Model):
    comment = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

class CommentedModelMixin(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel):
    class Meta:
        abstract = True

class Source(BaseModel, BaseCreatedByModel):
    name = models.CharField(max_length=255, unique=True)
    url = models.TextField(null=True, blank=True)
    reference = models.TextField(null=True, blank=True)

    def __str__(self):
        return str(self.name)

class BaseSourcedModel(models.Model):
    source_text = models.CharField(max_length=255, null=True, blank=True)
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True

class SourcedModelMixin(BaseTimestampedModel, BaseCreatedByModel, BaseCommentableModel, BaseSourcedModel):
    class Meta:
        abstract = True

class BaseLemmaModel(BaseModel):
    def lemmatize(self, lemma):
        # TODO call lemmatize API
        return lemma.split(" ")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        lemma = self.lemmatize(self.lemma)

        # TODO call word_types validate API
        word_types = self.word_types.split("|")

        if len(lemma) != len(word_types):
           raise ValidationError(
               {"word_types": "word_types needs to have as many '|' as the lemma has tokens"})

        for word_type in word_types:
            if word_type[0] in ("=", "~", "-"):
                word_type = word_type[1:]

            word_type = word_type.split("+")
            for sub_word_type in word_type:
                if sub_word_type != "s" and sub_word_type != "a" and sub_word_type != "adv" and sub_word_type != "v" and sub_word_type != "conj" and sub_word_type != "emoji":
                    raise ValidationError(
                        {"word_types": f"unrecognized word type '{sub_word_type}'."})

        self.lemma_json = lemma
        self.word_types_json = word_types

    class Meta:
        abstract = True

    lemma = models.CharField(max_length=255)
    lemma_json = models.JSONField(default=dict)
    word_types = models.CharField(max_length=255)
    word_types_json = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    label = models.TextField(null=True, blank=True)

class LanguageEnum(models.TextChoices):
    EN = 'en', 'English'
    DE = 'de', 'German'

class ContentEnum(models.TextChoices):
    BASIC = "basic"
    ADVANCED = "advanced"
    VIDEO = "video"

class ProficiencyLevelEnum(models.TextChoices):
    HATE = "hate"
    BASIC = "basic"
    ADVANCED = "advanced"

class Category(BaseModel, CommentedModelMixin):
    class Meta:
        verbose_name_plural = "categories"
    def __str__(self):
        return str(self.name)

    name = models.CharField(max_length=255, unique=True)

class DiversityDimension(BaseModel, CommentedModelMixin):
    def __str__(self):
        return str(self.name)

    name = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

class Rule(BaseLemmaModel, SourcedModelMixin):
    class Meta:
        unique_together = (("language", "lemma"),)

    def __str__(self):
        return str(self.lemma[0:50]  + " (" + self.language + ")")

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)

    is_context_aware = models.BooleanField(default=False)

    diversity_dimensions = models.ManyToManyField(DiversityDimension, through='RuleDiversityDimension')

    ownedby = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='owner')

class RuleDiversityDimension(OrderedModel, TimestampedModelMixin):
    class Meta:
        unique_together = (("rule", "diversity_dimension"),)
        ordering = ("order",)

    order_with_respect_to = 'rule'

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)
    diversity_dimension = models.ForeignKey(DiversityDimension, on_delete=models.CASCADE)

class Alternative(OrderedModel, BaseLemmaModel, SourcedModelMixin):
    class Meta:
        ordering = ("order",)

    def __str__(self):
        return str(self.lemma[0:50])

    order_with_respect_to = 'rule'

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    is_singular = models.BooleanField(default=True)
    is_inspiration = models.BooleanField(default=False)

class TrainingSentence(BaseModel, SourcedModelMixin):
    def __str__(self):
        return str(self.text)

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    text = models.TextField(null=True, blank=True)

    is_false_positive = models.BooleanField(default=False)
    is_training_data = models.BooleanField(default=False)
