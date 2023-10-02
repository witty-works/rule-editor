import sys

from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from django.urls import reverse, reverse_lazy

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

from .models import (
    Rule,
    Alternative,
    Category,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
    FalsePositive,
    TrainingSentence,
    Lemmatization,
    Verb,
    Adjective,
    Noun,
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


class TrainingSentenceInline(admin.StackedInline):
    model = TrainingSentence
    fields = (
        "text",
        "is_false_positive",
        "is_training_data",
        "comment",
    )


class RuleDiversityDimensionInline(OrderedStackedInline):
    model = RuleDiversityDimension
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
                link = reverse(f"admin:rules_{class_name.lower()}_change", args=[instance.pk])
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

    fields = (
        "lemma",
        "language",
        "text_id",
        "word_types",
        "is_marked_for_review",
        "is_context_aware",
        "type",
        "is_active",
        "label",
        "explanation",
        "emoji",
        "url",
        "tags",
        "source",
        "comment",
        "ownedby",
    )
    radio_fields = {"type": admin.HORIZONTAL}
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
    save_on_top = True

    inlines = [
        RuleDiversityDimensionInline,
        AlternativeInline,
        TrainingSentenceInline,
        FalsePositiveInline,
    ]


class CategoryResource(resources.ModelResource):
    class Meta:
        model = Category


@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin):
    class Meta:
        model = Category

    resource_class = CategoryResource
    search_fields = ("name",)


class DiversityDimensionResource(resources.ModelResource):
    class Meta:
        model = DiversityDimension


@admin.register(DiversityDimension)
class DiversityDimensionAdmin(OrderedModelAdmin, ImportExportModelAdmin):
    class Meta:
        model = DiversityDimension

    resource_class = DiversityDimensionResource
    list_display = ("name", "move_up_down_links")
    search_fields = ("name",)
    list_filter = (
        "category",
        "is_advanced",
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )


@admin.register(Source)
class SourceAdmin(CreatedByAdmin):
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
