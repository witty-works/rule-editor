from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

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

class DiversityDimension(BaseModel, CommentedModelMixin):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return str(self.name)

class Rule(SourcedModelMixin):
    class Meta:
        unique_together = (("language","lemma"),)

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)

    lemma = models.JSONField()
    word_types = models.JSONField()
    label = models.TextField(null=True, blank=True)

    is_inspiration = models.BooleanField(default=False)
    is_context_aware = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    diversity_dimensions = models.ManyToManyField(DiversityDimension, through='RuleDiversityDimension')

    ownedby = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='owner')

    def __str__(self):
        return str(self.lemma[0:50]  + " (" + self.language + ")")

class RuleDiversityDimension(OrderedModel, TimestampedModelMixin):
    class Meta:
        unique_together = (("rule", "diversity_dimension"),)
        ordering = ("order",)

    order_with_respect_to = 'rule'

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)
    diversity_dimension = models.ForeignKey(DiversityDimension, on_delete=models.CASCADE)

class Alternative(OrderedModel, SourcedModelMixin):
    class Meta:
        ordering = ("order",)

    order_with_respect_to = 'rule'

    language = EnumField(LanguageEnum, default=LanguageEnum.EN)

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    lemma = models.JSONField()
    word_types = models.JSONField()

    is_singular = models.BooleanField(default=True)
    is_inspiration = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    label = models.TextField(null=True, blank=True)

    def __str__(self):
        return str(self.lemma[0:50] + " (" + self.language + ")")

class TrainingSentence(BaseModel, SourcedModelMixin):
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE)

    text = models.TextField(null=True, blank=True)

    is_false_positive = models.BooleanField(default=False)
    is_training_data = models.BooleanField(default=False)

    def __str__(self):
        return str(self.text)
