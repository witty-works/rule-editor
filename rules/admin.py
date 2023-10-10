import sys

from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from django.urls import reverse, reverse_lazy
from django.conf import settings

import requests
from requests.auth import HTTPBasicAuth
import json

from import_export import resources
from import_export.admin import ImportExportModelAdmin
from ordered_model.admin import (
    OrderedStackedInline,
    OrderedInlineModelAdminMixin,
    OrderedModelAdmin,
)
from rangefilter.filter import DateRangeFilter
from more_admin_filters import MultiSelectRelatedOnlyFilter
from dal import autocomplete
from taggit_bulk.actions import tag_wizard
from dynamic_forms import DynamicField, DynamicFormMixin

from .models import (
    Rule,
    Alternative,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
    FalsePositive,
    TrainingSentence,
    Lemmatization,
    Verb,
    Adjective,
    Noun,
    fetch_json,
)


def get_class(class_name):
    return getattr(sys.modules[__name__], class_name)


class CreatedByAdmin(admin.ModelAdmin):
    base_readonly_fields = "created_by"

    def save_model(self, request, obj, form, change):
        obj.createdby = request.user
        obj.save()


class AlternativeAdmin(CreatedByAdmin):
    class Meta:
        model = Alternative

    list_display = ("name", "move_up_down_links")


class AlternativeForm(forms.ModelForm):
    class Meta:
        widgets = {
            "tags": autocomplete.TaggitSelect2(
                url="tag-autocomplete",
                attrs={"class": "form-control", "data-placeholder": "Tag names .."},
            )
        }


class AlternativeInline(OrderedStackedInline):
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
        "move_up_down_links",
    )
    radio_fields = {"type": admin.HORIZONTAL, "pluralization": admin.HORIZONTAL}
    readonly_fields = ("move_up_down_links",)
    ordering = ("order",)
    extra = 1


class FalsePositiveInline(admin.StackedInline):
    model = FalsePositive
    fields = (
        "false_positive",
        "comment",
    )


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


class RuleDiversityDimensionInline(OrderedStackedInline):
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
        "move_up_down_links",
    )
    readonly_fields = ("move_up_down_links",)
    ordering = ("order",)
    extra = 1


@admin.register(Rule)
class RuleAdmin(OrderedInlineModelAdminMixin, CreatedByAdmin):
    class Meta:
        model = Rule

    def all_diversity_dimensions(self, obj):
        return ", ".join([d.name for d in obj.diversity_dimensions.all()])

    def generate_help_text(self, class_name, filters, token):
        cls = get_class(class_name)
        instances = cls.objects.filter(**filters)
        if instances:
            for instance in instances:
                link = reverse(
                    f"admin:rules_{class_name.lower()}_change", args=[instance.pk]
                )
                return (
                    f"{class_name} <a href=\"{link}\">data available</a> for '{token}'"
                )

        return f"No {class_name} data available for '{token}'"

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        help_text = []
        if obj:
            tokens = obj.tokenize()
            word_types = obj.parse_word_type()
            for i in range(len(word_types)):
                if word_types[i]["lemmatize"]:
                    filters = {"language": obj.language}
                    if word_types[i]["lower_case"]:
                        filters["base_form"] = tokens[i]
                    else:
                        filters["base_form__iexact"] = tokens[i]

                    if "v" in word_types[i]["word_types"]:
                        help_text.append(
                            self.generate_help_text("Verb", filters, tokens[i])
                        )
                    if "a" in word_types[i]["word_types"]:
                        help_text.append(
                            self.generate_help_text("Adjective", filters, tokens[i])
                        )
                    if "s" in word_types[i]["word_types"]:
                        help_text.append(
                            self.generate_help_text("Noun", filters, tokens[i])
                        )

                    filters = {"lemma": tokens[i], "language": obj.language}
                    help_text.append(
                        self.generate_help_text("Lemmatization", filters, tokens[i])
                    )

        if len(help_text):
            form.base_fields["lemma"].help_text = mark_safe("<br>".join(help_text))

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
        "language",
        "lemma",
    )
    list_filter = (
        "language",
        "is_marked_for_review",
        "tags",
        "is_active",
        ("diversity_dimensions", MultiSelectRelatedOnlyFilter),
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )
    list_display = (
        "lemma",
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
class DiversityDimensionAdmin(OrderedModelAdmin):
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

    list_display = ("name", "move_up_down_links")
    search_fields = ("name",)
    list_filter = (
        "category",
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


class VerbResource(resources.ModelResource):
    class Meta:
        model = Verb


@admin.register(Verb)
class VerbAdmin(ImportExportModelAdmin):
    class Meta:
        model = Verb

    resource_class = VerbResource
    search_fields = ("base_form",)
    list_filter = ("language",)


class AdjectiveResource(resources.ModelResource):
    class Meta:
        model = Adjective


@admin.register(Adjective)
class AdjectiveAdmin(ImportExportModelAdmin):
    class Meta:
        model = Adjective

    resource_class = AdjectiveResource
    search_fields = ("base_form",)
    list_filter = ("language",)


class NounResource(resources.ModelResource):
    class Meta:
        model = Noun


@admin.register(Noun)
class NounAdmin(ImportExportModelAdmin):
    class Meta:
        model = Noun

    resource_class = NounResource
    search_fields = ("base_form",)
    list_filter = ("language",)
