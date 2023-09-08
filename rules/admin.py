from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin
from ordered_model.admin import (
    OrderedStackedInline,
    OrderedInlineModelAdminMixin,
    OrderedModelAdmin,
)
from rangefilter.filter import DateRangeFilter

from .models import (
    Rule,
    Alternative,
    Category,
    DiversityDimension,
    RuleDiversityDimension,
    Source,
    FalsePositive,
    TrainingSentence,
)


class CreatedByAdmin(admin.ModelAdmin):
    base_readonly_fields = "created_by"

    def save_model(self, request, obj, form, change):
        obj.createdby = request.user
        obj.save()


class AlternativeAdmin(CreatedByAdmin):
    class Meta:
        model = Alternative

    list_display = ("name", "move_up_down_links")


class AlternativeInline(OrderedStackedInline):
    model = Alternative
    fields = (
        "lemma",
        "word_types",
        "is_singular",
        "is_inspiration",
        "is_active",
        "label",
        "source",
        "comment",
        "move_up_down_links",
    )
    readonly_fields = ("move_up_down_links",)
    ordering = ("order",)
    extra = 1


class FalsePositiveInline(admin.StackedInline):
    model = FalsePositive
    fields = (
        "name",
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
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )


class RuleDiversityDimensionInline(OrderedStackedInline):
    model = RuleDiversityDimension
    fields = (
        "diversity_dimension",
        "is_advanced",
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
        all_diversity_dimensions = []
        for rdd in obj.rulediversitydimension_set.all():
            text = rdd.diversity_dimension.name
            if rdd.is_advanced:
                text += " (a)"
            all_diversity_dimensions.append(text)

        return ", ".join(all_diversity_dimensions)

    fields = (
        "language",
        "lemma",
        "word_types",
        "is_context_aware",
        "is_prefix",
        "is_active",
        "label",
        "source",
        "comment",
        "ownedby",
    )
    search_fields = (
        "language",
        "lemma",
    )
    list_filter = (
        "language",
        "diversity_dimensions",
        "is_active",
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )
    list_display = ("language", "lemma", "is_active", "all_diversity_dimensions")
    save_on_top = True

    inlines = [
        RuleDiversityDimensionInline,
        AlternativeInline,
        FalsePositiveInline,
        TrainingSentenceInline,
    ]


@admin.register(Source)
class SourceAdmin(CreatedByAdmin):
    class Meta:
        model = Source

    search_fields = ("name", "url", "reference")
    list_filter = (
        ("created_at", DateRangeFilter),
        ("updated_at", DateRangeFilter),
    )
