import sys

from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from django.urls import reverse, reverse_lazy
from django.conf import settings
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ValidationError

import requests
import json

from import_export import resources
from import_export.admin import ImportExportModelAdmin
from rangefilter.filter import DateRangeFilter
from more_admin_filters import MultiSelectRelatedOnlyFilter
from dal import autocomplete
from taggit_bulk.actions import tag_wizard
from dynamic_forms import DynamicField, DynamicFormMixin
from grappelli.forms import GrappelliSortableHiddenMixin

from .models import (
    Rule,
    Alternative,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
    FalsePositive,
    TrainingSentence,
    Lemmatization,
    EnglishVerb,
    EnglishAdjective,
    EnglishNoun,
    GermanVerb,
    GermanAdjective,
    GermanNoun,
    fetch_json,
)


def get_class(class_name):
    return getattr(sys.modules[__name__], class_name)


def generate_help_text(name, language, filters, token):
    match language:
        case "de":
            class_name = "German" + name
        case "en":
            class_name = "English" + name
        case _:
            class_name = name

    cls = get_class(class_name)
    instances = cls.objects.filter(**filters)
    if instances:
        help_texts = []
        for instance in instances:
            if isinstance(instance, Alternative):
                link = reverse(f"admin:rules_rule_change", args=[instance.rule.id])
            else:
                link = reverse(
                    f"admin:rules_{class_name.lower()}_change", args=[instance.pk]
                )

            word = instance.lemma if isinstance(instance, Rule) else token
            help_texts.append(
                f"{name} <a href=\"{link}\">data available</a> for '{word}'"
            )

        return "<br>".join(help_texts)

    return f"No {name} data available for '{token}'"


def update_lemma_help_text(obj, field):
    help_texts = [field.help_text]

    try:
        tokens, lemmas = obj.tokenize()
        word_types = obj.parse_word_types()
        if word_types is None:
            return
    except ValidationError as exception:
        help_texts.append(
            "<b>Tokenization/Word_types validation failed</b>: " + exception.message
        )

        tokens = lemmas = word_types = []

    word_type_map = {
        "v": "Verb",
        "a": "Adjective",
        "n": "Noun",
    }

    for i in range(len(word_types)):
        if word_types[i]["lemmatize"]:
            if tokens[i] != lemmas[i]:
                help_texts.append(
                    f"<strong>Token '{tokens[i]}' does not match lemma '{lemmas[i]}'</strong>"
                )
            key = "base_form" if word_types[i]["lower_case"] else "base_form__iexact"
            filters = {key: tokens[i]}

            for word_type in word_type_map:
                if word_type in word_types[i]["word_type"]:
                    help_texts.append(
                        generate_help_text(
                            word_type_map[word_type], obj.language, filters, tokens[i]
                        )
                    )

            filters = {"lemma": tokens[i], "language": obj.language}
            help_texts.append(
                generate_help_text("Lemmatization", None, filters, tokens[i])
            )

    field.help_text = mark_safe("<br>".join(help_texts))


def update_base_form_help_text(obj, field, language):
    help_texts = [field.help_text]

    filters = {
        "lemma__regex": "\\b(?<!-)" + obj.base_form + "(?!-)\\b",
        "language": language,
    }
    help_texts.append(generate_help_text("Rule", None, filters, obj.base_form))
    help_texts.append(generate_help_text("Alternative", None, filters, obj.base_form))

    field.help_text = mark_safe("<br>".join(help_texts))


class CreatedByAdmin(admin.ModelAdmin):
    base_readonly_fields = "created_by"

    def save_model(self, request, obj, form, change):
        obj.createdby = request.user
        obj.save()


class AlternativeAdmin(CreatedByAdmin):
    class Meta:
        model = Alternative


class AlternativeForm(forms.ModelForm):
    class Meta:
        widgets = {
            "tags": autocomplete.TaggitSelect2(
                url="tag-autocomplete",
                attrs={"class": "form-control", "data-placeholder": "Tag names .."},
            )
        }

    def __init__(self, *args, **kwargs):
        super(AlternativeForm, self).__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and isinstance(instance, Alternative):
            update_lemma_help_text(instance, self.fields["lemma"])


class AlternativeInline(GrappelliSortableHiddenMixin, admin.StackedInline):
    model = Alternative
    form = AlternativeForm
    fields = (
        "lemma",
        "word_types",
        "is_remove",
        "is_inspiration",
        "is_advanced",
        "pluralization",
        "type",
        "is_active",
        "label",
        "tags",
        "source",
        "comment",
        "order",
    )
    radio_fields = {"type": admin.HORIZONTAL, "pluralization": admin.HORIZONTAL}
    ordering = ("order",)
    extra = 0
    sortable_field_name = "order"


class FalsePositiveInline(admin.StackedInline):
    model = FalsePositive
    fields = (
        "false_positive",
        "comment",
    )
    extra = 0


def apply_rule(values):
    if values is None or "rule" not in values or "text" not in values:
        return None

    rule = Rule.objects.get(pk=values["rule"])

    alternatives = []
    for alternative in rule.alternatives.all():
        alternative = {
            "lemma": alternative.lemma,
            "word_types": alternative.word_types,
            "type": str(alternative.type),
            "pluralization": str(alternative.pluralization),
            "is_inspiration": alternative.is_inspiration,
            "is_advanced": alternative.is_advanced,
        }
        alternatives.append(alternative)

    false_positives = []
    for false_positive in rule.false_positives.all():
        false_positives.append(false_positive.false_positive)

    data = {
        "text": values["text"],
        "lang": str(rule.language),
        "lemma": rule.lemma,
        "word_types": rule.word_types,
        "subcategories": rule.diversity_dimension_json,
        "lower_case": True,
        "alternatives": alternatives,
        "false_positives": false_positives,
    }

    path = "/debug/rule"
    return fetch_json(path, data)


def apply_spacy(values):
    if values is None or "rule" not in values or "text" not in values:
        return None

    rule = Rule.objects.get(pk=values["rule"])

    text = values["text"]
    path = f"/debug/spacy?lang={requests.utils.quote(rule.language)}&text={requests.utils.quote(text)}"
    return fetch_json(path)


from django.template.loader import render_to_string
import hashlib


def visualize_sentence(values):
    if values is None or "rule" not in values or "text" not in values:
        return None

    rule = Rule.objects.get(pk=values["rule"])

    text = values["text"]
    path = f"/debug/displacy?lang={requests.utils.quote(rule.language)}&text={requests.utils.quote(text)}"
    url = settings.NLP_API + path
    sentence_hash = hashlib.md5(text.encode()).hexdigest()

    html = render_to_string(
        "admin/displacy.html",
        context={"url": mark_safe(url), "id": mark_safe(sentence_hash)},
    )

    return mark_safe(html)


class PrettyJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, indent, sort_keys, **kwargs):
        super().__init__(*args, indent=2, sort_keys=True, **kwargs)


class TrainingSentenceForm(DynamicFormMixin, forms.ModelForm):
    response = DynamicField(
        forms.JSONField,
        disabled=True,
        required=False,
        initial=lambda form: apply_rule(form.initial),
        encoder=lambda form: PrettyJSONEncoder,
    )
    spacy = DynamicField(
        forms.JSONField,
        disabled=True,
        required=False,
        initial=lambda form: apply_spacy(form.initial),
        encoder=lambda form: PrettyJSONEncoder,
        help_text=lambda form: visualize_sentence(form.initial),
    )


class TrainingSentenceInline(admin.StackedInline):
    model = TrainingSentence
    form = TrainingSentenceForm
    fields = (
        "text",
        "is_false_positive",
        "is_training_data",
        "comment",
        "spacy",
        "response",
    )
    extra = 0


class RuleDiversityDimensionForm(forms.ModelForm):
    class Meta:
        widgets = {
            "diversity_dimension": autocomplete.ModelSelect2(
                url="diversity_dimension-autocomplete",
                attrs={
                    "class": "form-control",
                    "data-placeholder": "Diversity dimensions ..",
                },
            )
        }


class RuleDiversityDimensionInline(GrappelliSortableHiddenMixin, admin.StackedInline):
    def get_formset(self, request, obj=None, **kwargs):
        res = super().get_formset(request, obj=None, **kwargs)
        for formfield in res.form.base_fields.values():
            if hasattr(formfield, "widget"):
                formfield.widget.can_add_related = False
                formfield.widget.can_delete_related = False
                formfield.widget.can_change_related = False
        return res

    model = RuleDiversityDimension
    form = RuleDiversityDimensionForm
    fields = (
        "diversity_dimension",
        "order",
    )
    ordering = ("order",)
    sortable_field_name = "order"
    extra = 0


class InputFilter(admin.SimpleListFilter):
    template = "admin/input_filter.html"

    def lookups(self, request, model_admin):
        # Dummy, required to show the filter.
        return ((),)

    def choices(self, changelist):
        # Grab only the "all" option.
        all_choice = next(super().choices(changelist))
        all_choice["query_parts"] = (
            (k, v)
            for k, v in changelist.get_filters_params().items()
            if k != self.parameter_name
        )
        yield all_choice


class LemmaFilter(InputFilter):
    parameter_name = "lemma"
    title = "Lemma"

    def queryset(self, request, queryset):
        if self.value() is not None:
            lemma = self.value()

            return queryset.filter(Q(lemma=lemma))


@admin.register(Rule)
class RuleAdmin(CreatedByAdmin):
    class Meta:
        model = Rule

    def all_diversity_dimensions(self, obj):
        return ", ".join([d.name for d in obj.diversity_dimensions.all()])

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_lemma_help_text(obj, form.base_fields["lemma"])

        form.base_fields["tags"].widget = autocomplete.TaggitSelect2(
            url=reverse_lazy("tag-autocomplete"),
            attrs={"class": "form-control", "data-placeholder": "Tag names .."},
        )

        return form

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    def tag_list(self, obj):
        return ", ".join(o.name for o in obj.tags.all())

    actions = [tag_wizard]

    fieldsets = (
        (
            "",
            {
                "fields": (
                    "lemma",
                    "language",
                    "text_id",
                    "word_types",
                    "is_marked_for_review",
                    "is_context_aware",
                    "type",
                    "is_active",
                    "tags",
                ),
            },
        ),
        (
            "Custom Label",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": (
                    "label_type",
                    "label",
                    "explanation",
                    "emoji",
                    "url",
                ),
            },
        ),
        (
            "Optional Fields",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": (
                    "source",
                    "comment",
                    "ownedby",
                ),
            },
        ),
    )

    radio_fields = {"type": admin.HORIZONTAL, "label_type": admin.HORIZONTAL}
    search_fields = (
        "lemma",
        "comment",
        "label_type",
        "label",
        "alternatives__lemma",
    )
    list_filter = (
        LemmaFilter,
        "language",
        "is_marked_for_review",
        "tags",
        "is_active",
        "type",
        "label_type",
        "has_training_sentences",
        ("diversity_dimensions", MultiSelectRelatedOnlyFilter),
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )
    list_display = (
        "lemma",
        "word_types",
        "language",
        "is_active",
        "all_diversity_dimensions",
        "tag_list",
    )

    inlines = [
        RuleDiversityDimensionInline,
        AlternativeInline,
        TrainingSentenceInline,
        FalsePositiveInline,
    ]


@admin.register(DiversityDimension)
class DiversityDimensionAdmin(admin.ModelAdmin):
    class Meta:
        model = DiversityDimension

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)

    def get_list_display_links(self, request, list_display):
        super().get_list_display_links(request, list_display)
        return None

    def has_add_permission(self, request, obj=None):  # Here
        return False

    list_display = ("name", "category", "proficiency_level")
    search_fields = ("name",)
    list_filter = (
        "category",
        "proficiency_level",
        "is_advanced",
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )


class SourceResource(resources.ModelResource):
    class Meta:
        model = Source


@admin.register(Source)
class SourceAdmin(CreatedByAdmin, ImportExportModelAdmin):
    class Meta:
        model = Source

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        form.base_fields["tags"].widget = autocomplete.TaggitSelect2(
            url=reverse_lazy("tag-autocomplete"),
            attrs={"class": "form-control", "data-placeholder": "Tag names .."},
        )

        return form

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    def tag_list(self, obj):
        return ", ".join(o.name for o in obj.tags.all())

    actions = [tag_wizard]

    resource_class = SourceResource

    fields = ("name", "url", "tags", "reference", "comment")
    list_display = (
        "name",
        "tag_list",
    )
    search_fields = ("name", "url", "reference")
    list_filter = (
        "tags",
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )


class LemmatizationResource(resources.ModelResource):
    class Meta:
        model = Lemmatization


@admin.register(Lemmatization)
class LemmatizationAdmin(ImportExportModelAdmin):
    class Meta:
        model = Lemmatization

    resource_class = LemmatizationResource

    fields = ("text", "lemma", "language", "comment")
    search_fields = ("text", "lemma")
    list_filter = ("language",)
    list_display = (
        "text",
        "lemma",
        "language",
    )


class EnglishVerbResource(resources.ModelResource):
    class Meta:
        model = EnglishVerb


@admin.register(EnglishVerb)
class EnglishVerbAdmin(ImportExportModelAdmin):
    class Meta:
        model = EnglishVerb

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"], "en")

        return form

    resource_class = EnglishVerbResource
    search_fields = ("base_form",)
    fields = (
        "base_form",
        "present_participle",
        "third_person_singular",
        "past_tense",
        "past_participle",
        "comment",
    )
    list_display = (
        "base_form",
        "present_participle",
        "third_person_singular",
        "past_tense",
        "past_participle",
    )


class EnglishAdjectiveResource(resources.ModelResource):
    class Meta:
        model = EnglishAdjective


@admin.register(EnglishAdjective)
class EnglishAdjectiveAdmin(ImportExportModelAdmin):
    class Meta:
        model = EnglishAdjective

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"], "en")

        return form

    resource_class = EnglishAdjectiveResource
    search_fields = ("base_form",)
    fields = ("base_form", "comparative", "superlative", "is_absolute", "comment")
    list_display = ("base_form", "comparative", "superlative", "is_absolute")


class EnglishNounResource(resources.ModelResource):
    class Meta:
        model = EnglishNoun


@admin.register(EnglishNoun)
class NounAdmin(ImportExportModelAdmin):
    class Meta:
        model = EnglishNoun

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"], "en")

        return form

    resource_class = EnglishNounResource
    search_fields = ("base_form",)
    fields = ("base_form", "plural", "comment")
    list_display = (
        "base_form",
        "plural",
    )


class GermanVerbResource(resources.ModelResource):
    class Meta:
        model = GermanVerb


@admin.register(GermanVerb)
class GermanVerbAdmin(ImportExportModelAdmin):
    class Meta:
        model = GermanVerb

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"], "en")

        return form

    resource_class = GermanVerbResource
    search_fields = ("base_form",)
    fields = ("base_form", "comment")
    list_display = ("base_form",)


class GermanAdjectiveResource(resources.ModelResource):
    class Meta:
        model = GermanAdjective


@admin.register(GermanAdjective)
class GermanAdjectiveAdmin(ImportExportModelAdmin):
    class Meta:
        model = GermanAdjective

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"], "en")

        return form

    resource_class = GermanAdjectiveResource
    search_fields = ("base_form",)
    fields = ("base_form", "comment")
    list_display = ("base_form",)


class GermanNounResource(resources.ModelResource):
    class Meta:
        model = GermanNoun


@admin.register(GermanNoun)
class NounAdmin(ImportExportModelAdmin):
    class Meta:
        model = GermanNoun

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"], "en")

        return form

    resource_class = GermanNounResource
    search_fields = ("base_form",)
    fields = ("base_form", "comment")
    list_display = ("base_form",)
