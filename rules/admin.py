import sys

from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from django.urls import reverse, reverse_lazy, NoReverseMatch
from django.shortcuts import redirect
from django.conf import settings
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Lookup
from django.db.models import Field
from django.contrib import messages
from django.db import connection
from django.http import HttpResponseRedirect
from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.utils.html import escape
from django.contrib.auth.models import User


import requests
import json

from import_export import resources
from import_export.admin import ImportExportModelAdmin
from rangefilter.filters import DateRangeFilter
from more_admin_filters import MultiSelectRelatedOnlyFilter
from dal import autocomplete, forward
from taggit_bulk.actions import tag_wizard
from dynamic_forms import DynamicField, DynamicFormMixin
from grappelli.forms import GrappelliSortableHiddenMixin
import nested_admin

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
    LanguageEnum,
    fetch_json,
)

stopwords = {
    "de": [
        "aber",
        "als",
        "am",
        "an",
        "auch",
        "auf",
        "aus",
        "bei",
        "bin",
        "bis",
        "bist",
        "da",
        "dadurch",
        "daher",
        "darum",
        "das",
        "daß",
        "dass",
        "dein",
        "deine",
        "dem",
        "den",
        "der",
        "des",
        "dessen",
        "deshalb",
        "die",
        "dies",
        "dieser",
        "dieses",
        "doch",
        "dort",
        "du",
        "durch",
        "ein",
        "eine",
        "einem",
        "einen",
        "einer",
        "eines",
        "er",
        "es",
        "euer",
        "eure",
        "für",
        "hatte",
        "hatten",
        "hattest",
        "hattet",
        "hier",
        "hinter",
        "ich",
        "ihr",
        "ihre",
        "im",
        "in",
        "ist",
        "ja",
        "jede",
        "jedem",
        "jeden",
        "jeder",
        "jedes",
        "jener",
        "jenes",
        "jetzt",
        "kann",
        "kannst",
        "können",
        "könnt",
        "machen",
        "mein",
        "meine",
        "mit",
        "muß",
        "mußt",
        "musst",
        "müssen",
        "müßt",
        "nach",
        "nachdem",
        "nein",
        "nicht",
        "nun",
        "oder",
        "seid",
        "sein",
        "seine",
        "sich",
        "sie",
        "sind",
        "soll",
        "sollen",
        "sollst",
        "sollt",
        "sonst",
        "soweit",
        "sowie",
        "und",
        "unser",
        "unsere",
        "unter",
        "vom",
        "von",
        "vor",
        "wann",
        "warum",
        "was",
        "weiter",
        "weitere",
        "wenn",
        "wer",
        "werde",
        "werden",
        "werdet",
        "weshalb",
        "wie",
        "wieder",
        "wieso",
        "wir",
        "wird",
        "wirst",
        "wo",
        "woher",
        "wohin",
        "zu",
        "zum",
        "zur",
        "über",
    ],
    "en": [
        "a",
        "about",
        "an",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "who",
        "will",
        "with",
        "the",
    ],
}


def get_class(class_name):
    return getattr(sys.modules[__name__], class_name)


@Field.register_lookup
class NotEqual(Lookup):
    lookup_name = "ne"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return "%s <> %s" % (lhs, rhs), params


def generate_help_text(name, language, filters, token, text="", recurse=True):
    if token.startswith("~"):
        token = token[1:]

    if "~" in token:
        return ""

    class_name = name
    if class_name in ["Verb", "Adjective", "Noun"]:
        class_name = ("German" if language == "de" else "English") + class_name

    text = "" if text == "" else f" '{text}'"

    cls = get_class(class_name)
    instances = cls.objects.filter(**filters)
    if instances:
        help_texts = []
        for instance in instances:
            if isinstance(instance, Alternative):
                link = reverse(f"admin:rules_rule_change", args=[instance.rule.id])
            elif isinstance(instance, Rule):
                link = reverse(f"admin:rules_rule_change", args=[instance.id])
            else:
                link = reverse(
                    f"admin:rules_{class_name.lower()}_change", args=[instance.pk]
                )

            word = instance.lemma if isinstance(instance, Rule) else token
            word = f"'{word}'" if word == token else f"'{token}' ({word})"
            help_texts.append(
                f'{name} <a href="{link}">data available</a> for {word}{text}'
            )

            if recurse and class_name == "GermanNoun":
                if instance.male_form:
                    other_form = instance.male_form
                    text = "Male Form"
                elif instance.female_form:
                    other_form = instance.female_form
                    text = "Female Form"
                else:
                    other_form = None

                if other_form:
                    filters = {"base_form": other_form}
                    help_texts.append(
                        generate_help_text(
                            name, language, filters, other_form, text, False
                        )
                    )

        return "<br>".join(help_texts)

    text = text if text else "data available"
    return f"No {name} {text} for '{token}'"


def update_lemma_help_text(obj, language, field, type):
    help_texts = [field.help_text]

    if type == "alternative":
        help_texts.append("German Gender Lemma (check 'is gendered noun'): ~Male Form~")

    if language == "de" and type == "alternative" and obj.is_gendered_noun:
        variations = apply_german_gender_ending(obj.lemma)
        help_texts.append(
            "<br><b>German Gender Variations:</b><br>" + "<br>".join(variations)
        )

    try:
        tokens, lemmas, generated_word_types = obj.tokenize()
        message = (
            f"<br>Auto-detected word_types: {generated_word_types}"
            if obj.word_types == generated_word_types
            else f"<br><b>Auto-detected word_types mismatch: {generated_word_types}</b>"
        )
        help_texts.append(message)

        word_types = obj.parse_word_types()
    except ValidationError as exception:
        help_texts.append(
            "<br><b>Tokenization/Word_types validation failed</b>: " + exception.message
        )

        tokens = lemmas = word_types = []

    word_type_map = {
        "v": "Verb",
        "a": "Adjective",
        "n": "Noun",
    }

    for i in range(len(tokens)):
        if word_types is not None and word_types[i]["lemmatize"]:
            token = tokens[i]
            if token != lemmas[i]:
                help_texts.append(
                    f"<strong>Token '{tokens[i]}' does not match lemma '{lemmas[i]}'</strong>"
                )
            key = "base_form" if word_types[i]["lower_case"] else "base_form__iexact"
            filters = {key: token.strip("~")}

            for word_type in word_type_map:
                if word_type in word_types[i]["word_type"]:
                    help_texts.append(
                        generate_help_text(
                            word_type_map[word_type],
                            obj.language,
                            filters,
                            tokens[i],
                        )
                    )

            filters = {"lemma": tokens[i].strip("~"), "language": obj.language}
            help_texts.append(
                generate_help_text("Lemmatization", obj.language, filters, tokens[i])
            )

        match type:
            case "rule":
                filters = {
                    "first_token__iexact": tokens[i],
                    "id__ne": obj.id,
                }

                help_texts.append(
                    generate_help_text(
                        "Rule",
                        obj.language,
                        filters,
                        tokens[i],
                        "overlapping rules with matching first token",
                    )
                )
            case "alternative":
                if (
                    len(lemmas[i]) > 1
                    and tokens[i] not in stopwords[obj.language]
                    and lemmas[i] not in stopwords[obj.language]
                    and not obj.is_gendered_noun
                ):
                    first_tokens = [
                        tokens[i],
                        tokens[i].lower(),
                    ]
                    if tokens[i] != lemmas[i]:
                        first_tokens.append(lemmas[i])
                        first_tokens.append(lemmas[i].lower())

                    filters = {
                        "first_token__in": first_tokens,
                        "language": obj.language,
                    }

                    help_texts.append(
                        generate_help_text(
                            "Rule",
                            obj.language,
                            filters,
                            tokens[i].strip("~"),
                            "potential circular alternative",
                        )
                    )

    field.help_text = mark_safe("<br>".join(help_texts))


def update_base_form_help_text(obj, field):
    help_texts = [field.help_text]

    if isinstance(obj, GermanNoun):
        language = "de"
        link = f'Open <a href="https://www.verbformen.de/konjugation/?w={obj.base_form}" target="_new">{obj.base_form}</a> on Verbformen'
    else:
        language = "de" if type(obj).__name__.startswith("German") else "en"
        link = f'Open <a href="https://{language}.wiktionary.org/wiki/{obj.base_form}" target="_new">{obj.base_form}</a> on Wikitionary'

    help_texts.append(link)

    if isinstance(obj, GermanNoun):
        if obj.female_form:
            filters = {"base_form": obj.female_form}
            help_texts.append(
                generate_help_text(
                    "Noun", "de", filters, obj.female_form, "Female Form", False
                )
            )
        elif obj.male_form:
            filters = {"base_form": obj.male_form}
            help_texts.append(
                generate_help_text(
                    "Noun", "de", filters, obj.male_form, "Male Form", False
                )
            )

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
            update_lemma_help_text(
                instance, instance.language, self.fields["lemma"], "alternative"
            )


class AlternativeInline(GrappelliSortableHiddenMixin, admin.StackedInline):
    model = Alternative
    form = AlternativeForm
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "lemma",
                    "word_types",
                    "is_remove",
                    "is_inspiration",
                    "is_collective_noun",
                    "is_gendered_noun",
                    "is_advanced",
                    "pluralization",
                    "type",
                    "is_active",
                    "label",
                    "order",
                ),
            },
        ),
        (
            "Optional Fields",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": (
                    "tags",
                    "source",
                    "sanctions",
                    "comment",
                ),
            },
        ),
    )
    radio_fields = {"type": admin.HORIZONTAL, "pluralization": admin.HORIZONTAL}
    filter_horizontal = ("sanctions",)
    ordering = ("order",)
    extra = 0
    sortable_field_name = "order"


class FalsePositiveInline(nested_admin.NestedStackedInline):
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

    rule_alternatives = rule.parent.alternatives if rule.parent else rule.alternatives

    alternatives = []
    for alternative in rule_alternatives.all().order_by("order"):
        alternative = {
            "lemma": alternative.lemma,
            "word_types": alternative.word_types_json,
            "type": str(alternative.type),
            "pluralization": str(alternative.pluralization),
            "is_inspiration": alternative.is_inspiration,
            "is_advanced": alternative.is_advanced,
            "is_remove": alternative.is_remove,
            "is_collective_noun": alternative.is_collective_noun,
            "is_gendered_noun": alternative.is_gendered_noun,
        }
        alternatives.append(alternative)

    false_positives = []
    for false_positive in rule.false_positives.all():
        false_positives.append(false_positive.false_positive)

    lemmatizations = {}
    for token in rule.lemma_json:
        token_lemmatizations = Lemmatization.objects.filter(
            lemma=token, language=rule.language
        )
        if token_lemmatizations is None:
            continue

        for token_lemmatization in token_lemmatizations:
            lemmatizations[token_lemmatization.text] = token_lemmatization.lemma

    data = {
        "text": values["text"],
        "lang": str(rule.language),
        "lemma": rule.lemma,
        "type": rule.type,
        "word_types": rule.word_types_json,
        "subcategories": rule.diversity_dimension_json,
        "alternatives": alternatives,
        "false_positives": false_positives,
        "label": rule.label,
        "pattern": rule.pattern,
        "is_pattern_match": rule.is_pattern_match,
        "entity_type": rule.entity_type,
        "pluralization": rule.pluralization,
        "lemmatizations": lemmatizations,
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


def apply_german_gender_ending(alternative):
    path = (
        f"/debug/german_gender_ending?alternative={requests.utils.quote(alternative)}"
    )
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


class TrainingSentenceInline(nested_admin.NestedStackedInline):
    model = TrainingSentence
    form = TrainingSentenceForm
    fields = (
        "text",
        "is_false_positive",
        "is_training_data",
        "alternative_expected",
        "is_on_website",
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


class RuleForm(forms.ModelForm):
    class Meta:
        widgets = {
            "parent": autocomplete.ModelSelect2(
                url="rule-autocomplete",
                forward=(
                    # Hacky workaround for https://github.com/yourlabs/django-autocomplete-light/issues/1346
                    forward.Field("children-__prefix__-parent", "ignore_id"),
                    forward.Field("language"),
                ),
                attrs={
                    "class": "form-control",
                    "data-placeholder": "Parent rule ..",
                },
            )
        }

    def __init__(self, *args, **kwargs):
        super(RuleForm, self).__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and isinstance(instance, Rule):
            update_lemma_help_text(
                instance, instance.language, self.fields["lemma"], "rule"
            )

    remove_from_parent = forms.BooleanField(required=False)


class ParentRuleInline(nested_admin.NestedStackedInline):
    def remove_from_parent(self, obj):
        return False

    model = Rule
    form = RuleForm
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "text_id",
                    "lemma",
                    "word_types",
                    "pattern",
                    "is_pattern_match",
                    "is_marked_for_review",
                    "is_context_aware",
                    "is_hr_rule",
                    "has_failing_training_sentence",
                    "type",
                    "entity_type",
                    "pluralization",
                    "is_active",
                    "remove_from_parent",
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
                    "tags",
                    "source",
                    "sanctions",
                    "comment",
                    "ownedby",
                ),
            },
        ),
    )

    extra = 0
    inlines = [
        TrainingSentenceInline,
        FalsePositiveInline,
    ]


@admin.register(Rule)
class RuleAdmin(nested_admin.NestedModelAdmin, CreatedByAdmin):
    class Meta:
        model = Rule

    form = RuleForm

    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            rule = Rule.objects.get(pk=object_id)
            if rule.parent is not None:
                return redirect(
                    reverse(f"admin:rules_rule_change", args=[rule.parent.id])
                )
        except Rule.DoesNotExist:
            pass

        return super().change_view(
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )

    def save_formset(self, request, form, formset, change):
        super(RuleAdmin, self).save_formset(request, form, formset, change)

        rule = formset.instance

        for data in formset.cleaned_data:
            if "remove_from_parent" in data and data["remove_from_parent"]:
                data["id"].parent = None
                data["id"].save()

        if (
            formset.prefix == "rulediversitydimension_set"
            and len(rule.diversity_dimensions.all()) == 0
        ):
            message = "Diversity dimensions missing"
            messages.add_message(request, messages.INFO, message)

        if formset.prefix == "alternatives" and len(rule.alternatives.all()) == 0:
            message = "Alternatives missing"
            messages.add_message(request, messages.INFO, message)

    def all_diversity_dimensions(self, obj):
        return ", ".join(obj.diversity_dimension_json)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        form.base_fields["parent"].widget.can_add_related = False
        form.base_fields["parent"].widget.can_delete_related = False

        if obj and obj.children.count():
            form.base_fields["parent"].disabled = True

        form.base_fields["tags"].widget = autocomplete.TaggitSelect2(
            url=reverse_lazy("tag-autocomplete"),
            attrs={"class": "form-control", "data-placeholder": "Tag names .."},
        )

        return form

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.is_active:
            diversity_dimensions = obj.diversity_dimensions.all()

            if diversity_dimensions.count() == 0:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "Rule must have a diversity dimension when marked active!",
                )
            else:
                has_non_inclusive = None
                has_inclusive = None
                for diversity_dimension in diversity_dimensions:
                    if diversity_dimension.proficiency_level == "inclusive":
                        has_inclusive = True
                    else:
                        has_non_inclusive = True

                if has_non_inclusive and obj.alternatives.count() == 0:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        "Rule with non-inclusive diversity dimension should have an alternative if marked active!",
                    )

                if has_non_inclusive and has_inclusive:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        "Rule should not mix inclusive and non-inclusive diversity dimensions when marked active!",
                    )

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
                    "language",
                    "text_id",
                    "lemma",
                    "word_types",
                    "pattern",
                    "is_pattern_match",
                    "is_marked_for_review",
                    "is_context_aware",
                    "is_hr_rule",
                    "has_failing_training_sentence",
                    "type",
                    "entity_type",
                    "pluralization",
                    "is_active",
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
                    "parent",
                    "links",
                    "tags",
                    "source",
                    "sanctions",
                    "comment",
                    "ownedby",
                ),
            },
        ),
    )

    radio_fields = {
        "type": admin.HORIZONTAL,
        "entity_type": admin.HORIZONTAL,
        "label_type": admin.HORIZONTAL,
        "pluralization": admin.HORIZONTAL,
    }
    filter_horizontal = (
        "links",
        "sanctions",
    )
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
        "is_hr_rule",
        "tags",
        "is_active",
        "type",
        "label_type",
        "first_word_type",
        "has_training_sentences",
        "has_failing_training_sentence",
        "source",
        "sanctions",
        ("diversity_dimensions", MultiSelectRelatedOnlyFilter),
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )
    list_display = (
        "lemma",
        "word_types",
        "language",
        "type",
        "is_active",
        "all_diversity_dimensions",
        "tag_list",
        "has_failing_training_sentence",
    )

    inlines = [
        ParentRuleInline,
        RuleDiversityDimensionInline,
        AlternativeInline,
        TrainingSentenceInline,
        FalsePositiveInline,
    ]
    save_as = True


@admin.register(DiversityDimension)
class DiversityDimensionAdmin(admin.ModelAdmin):
    list_per_page = 200

    class Meta:
        model = DiversityDimension

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def rule_count(self, obj):
        if not obj.has_rules:
            return ""

        count_values = []
        with connection.cursor() as cursor:
            for language in LanguageEnum:
                if not getattr(obj, f"has_{language}_rules", False):
                    continue

                url = getattr(obj, f"url_{language}")
                if url:
                    category = f'<a href="{url}" target="_new">{language}</a>'
                else:
                    category = language

                cursor.execute(
                    "SELECT count(*) FROM rules_rule WHERE is_active = 1 AND parent_id is NULL AND language = %s AND diversity_dimension_json LIKE %s",
                    [language, f'%["{obj.name}"%'],
                )
                count = cursor.fetchone()[0]
                url = f"/admin/rules/rule/?diversity_dimensions__id__in={str(obj.pk)}&language__exact={language}"
                if count < 5:
                    count = f'<span style="color: red">{count}</span>'
                filter_link = f'<a href="{url}" target="_new">{count}</a>'

                count_values.append(f"{category} ({filter_link})")

        return mark_safe(", ".join(count_values))

    def sentences(self, obj):
        sentences = []
        with connection.cursor() as cursor:
            if obj.proficiency_level == "openly_discriminating":
                sentences.append("'openly_discriminating' does not have examples")
            elif not obj.has_rules:
                sentences.append(
                    "Does not have explicit rules (harded or advanced alternatives only)"
                )
            else:
                for language in LanguageEnum:
                    cursor.execute(
                        "SELECT text, rule_id FROM rules_trainingsentence INNER JOIN rules_rule ON rules_trainingsentence.rule_id = rules_rule.id WHERE is_on_website = 1 AND language = %s AND diversity_dimension_json LIKE %s LIMIT 1",
                        [language, f'%"{obj.name}"%'],
                    )
                    sentence = cursor.fetchone()
                    if sentence is not None:
                        url = f"/admin/rules/rule/{sentence[1]}/change/"
                        link = f'<a href="{url}">{sentence[0]}</a>'
                        sentences.append(f"{language}: {link}")

        return mark_safe("<br>".join(sentences))

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}

        extra_context["show_delete"] = False

        return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = (
        "name",
        "external_name",
        "category",
        "proficiency_level",
        "has_en_rules",
        "has_de_rules",
        "rule_count",
        "sentences",
        "comment",
    )
    readonly_fields = (
        "name",
        "external_name",
        "parent_name",
        "category",
        "proficiency_level",
        "has_en_rules",
        "has_de_rules",
        "url_en",
        "url_de",
    )
    search_fields = (
        "name",
        "external_name",
    )
    admin_order_field = ("name", "category", "proficiency_level")
    list_filter = (
        "category",
        "proficiency_level",
        "is_advanced",
        "has_rules",
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

    fields = ("text", "lemma", "language", "is_plural", "comment")
    search_fields = ("text", "lemma")
    list_filter = ("language",)
    list_display = (
        "text",
        "lemma",
        "is_plural",
        "language",
    )


class DeclensionAdmin(ImportExportModelAdmin):
    change_form_template = "admin/change_form_fill_declensions.html"

    def response_change(self, request, obj):
        base_form = (
            request.POST["_declension_base"]
            if "_declension_base" in request.POST
            and len(request.POST["_declension_base"])
            else None
        )

        if "_fill_declensions_standard" in request.POST:
            _, message = obj.fill_declensions_standard(base_form)
            self.message_user(request, message)

            return HttpResponseRedirect(".")
        elif "_fill_declensions" in request.POST:
            _, message = obj.fill_declensions(base_form)
            self.message_user(request, message)

            return HttpResponseRedirect(".")
        return super().response_change(request, obj)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        if obj:
            update_base_form_help_text(obj, form.base_fields["base_form"])

        return form


class EnglishVerbResource(resources.ModelResource):
    class Meta:
        model = EnglishVerb


@admin.register(EnglishVerb)
class EnglishVerbAdmin(DeclensionAdmin):
    class Meta:
        model = EnglishVerb

    resource_class = EnglishVerbResource
    search_fields = (
        "base_form",
        "present_participle",
        "third_person_singular",
        "past_tense",
        "past_participle",
    )
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
class EnglishAdjectiveAdmin(DeclensionAdmin):
    class Meta:
        model = EnglishAdjective

    resource_class = EnglishAdjectiveResource
    search_fields = ("base_form", "comparative", "superlative")
    fields = ("base_form", "comparative", "superlative", "is_absolute", "comment")
    list_filter = (
        ("comparative", admin.EmptyFieldListFilter),
        "is_absolute",
    )
    list_display = ("base_form", "comparative", "superlative", "is_absolute")


class EnglishNounResource(resources.ModelResource):
    class Meta:
        model = EnglishNoun


@admin.register(EnglishNoun)
class EnglishNounAdmin(DeclensionAdmin):
    class Meta:
        model = EnglishNoun

    resource_class = EnglishNounResource
    search_fields = ("base_form", "plural", "plural_2")
    fields = ("base_form", "plural", "plural_2", "comment")
    list_display = (
        "base_form",
        "plural",
        "plural_2",
    )


class GermanVerbResource(resources.ModelResource):
    class Meta:
        model = GermanVerb


@admin.register(GermanVerb)
class GermanVerbAdmin(DeclensionAdmin):
    class Meta:
        model = GermanVerb

    resource_class = GermanVerbResource
    search_fields = (
        "base_form",
        "present_ich",
        "present_du",
        "present_pronoun",
        "past_tense_ich",
        "past_participle",
        "conjunctive_ich",
        "imperativ_singular",
        "imperativ_plural",
        "infinitiv_zu",
        "comment",
    )
    fields = (
        "base_form",
        "present_ich",
        "present_du",
        "present_pronoun",
        "past_tense_ich",
        "past_participle",
        "conjunctive_ich",
        "imperativ_singular",
        "imperativ_plural",
        "helping_verb",
        "infinitiv_zu",
        "comment",
    )
    list_filter = (
        "helping_verb",
        ("past_participle", admin.EmptyFieldListFilter),
    )
    list_display = (
        "base_form",
        "present_ich",
        "past_participle",
        "helping_verb",
        "infinitiv_zu",
    )


class GermanAdjectiveResource(resources.ModelResource):
    class Meta:
        model = GermanAdjective


@admin.register(GermanAdjective)
class GermanAdjectiveAdmin(DeclensionAdmin):
    class Meta:
        model = GermanAdjective

    resource_class = GermanAdjectiveResource
    search_fields = ("base_form", "comparative", "superlative")
    fields = ("base_form", "comparative", "superlative", "is_absolute", "comment")
    list_filter = (
        ("comparative", admin.EmptyFieldListFilter),
        "is_absolute",
    )
    list_display = ("base_form", "comparative", "superlative", "is_absolute")


class GermanNounResource(resources.ModelResource):
    class Meta:
        model = GermanNoun


@admin.register(GermanNoun)
class GermanNounAdmin(DeclensionAdmin):
    class Meta:
        model = GermanNoun

    resource_class = GermanNounResource
    search_fields = (
        "base_form",
        "female_form",
        "male_form",
        "singular_only",
        "plural_only",
        "sg_nom",
        "sg_dat",
        "sg_dat_2",
        "sg_gen",
        "sg_gen_2",
        "sg_acc",
        "pl_nom",
        "pl_dat",
        "pl_gen",
        "pl_acc",
        "collective_noun",
        "collective_noun_2",
    )
    fields = (
        "base_form",
        "female_form",
        "male_form",
        "gender_1",
        "gender_2",
        "singular_only",
        "plural_only",
        "sg_nom",
        "sg_dat",
        "sg_dat_2",
        "sg_gen",
        "sg_gen_2",
        "sg_acc",
        "pl_nom",
        "pl_dat",
        "pl_gen",
        "pl_acc",
        "collective_noun",
        "collective_noun_2",
        "comment",
    )
    list_filter = (
        ("sg_nom", admin.EmptyFieldListFilter),
        ("pl_nom", admin.EmptyFieldListFilter),
        ("gender_1", admin.EmptyFieldListFilter),
        ("male_form", admin.EmptyFieldListFilter),
        ("female_form", admin.EmptyFieldListFilter),
        ("collective_noun", admin.EmptyFieldListFilter),
        ("collective_noun_2", admin.EmptyFieldListFilter),
        "gender_1",
        "gender_2",
        "singular_only",
        "plural_only",
    )
    list_display = ("base_form", "female_form", "male_form", "gender_1")


action_names = {
    ADDITION: "Addition",
    CHANGE: "Change",
    DELETION: "Deletion",
}


class FilterBase(admin.SimpleListFilter):
    def queryset(self, request, queryset):
        if self.value():
            dictionary = dict(((self.parameter_name, self.value()),))
            return queryset.filter(**dictionary)


class ActionFilter(FilterBase):
    title = "action"
    parameter_name = "action_flag"

    def lookups(self, request, model_admin):
        return action_names.items()


class UserFilter(FilterBase):
    """Use this filter to only show current users, who appear in the log."""

    title = "user"
    parameter_name = "user_id"

    def lookups(self, request, model_admin):
        return tuple(
            (u.id, u.username)
            for u in User.objects.filter(
                pk__in=LogEntry.objects.values_list("user_id").distinct()
            )
        )


class AdminFilter(UserFilter):
    """Use this filter to only show current Superusers."""

    title = "admin"

    def lookups(self, request, model_admin):
        return tuple((u.id, u.username) for u in User.objects.filter(is_superuser=True))


class StaffFilter(UserFilter):
    """Use this filter to only show current Staff members."""

    title = "staff"

    def lookups(self, request, model_admin):
        return tuple((u.id, u.username) for u in User.objects.filter(is_staff=True))


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):

    date_hierarchy = "action_time"

    readonly_fields = ["object_link"] + [f.name for f in LogEntry._meta.get_fields()]

    list_filter = [
        UserFilter,
        ActionFilter,
        "content_type",
        # 'user',
    ]

    search_fields = ["object_repr", "change_message"]

    list_display = [
        "action_time",
        "user",
        "content_type",
        "object_link",
        "action_flag",
        "action_description",
        "change_message",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and request.method != "POST"

    def has_delete_permission(self, request, obj=None):
        return False

    def object_link(self, obj):
        ct = obj.content_type
        repr_ = escape(obj.object_repr)
        try:
            href = reverse(
                "admin:%s_%s_change" % (ct.app_label, ct.model), args=[obj.object_id]
            )
            link = '<a href="%s">%s</a>' % (href, repr_)
        except NoReverseMatch:
            link = repr_
        return mark_safe(link if obj.action_flag != DELETION else repr_)

    object_link.allow_tags = True
    object_link.admin_order_field = "object_repr"
    object_link.short_description = "object"

    def queryset(self, request):
        return (
            super(LogEntryAdmin, self)
            .queryset(request)
            .prefetch_related("content_type")
        )

    def action_description(self, obj):
        return action_names[obj.action_flag]

    action_description.short_description = "Action"
