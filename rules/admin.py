from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin
from ordered_model.admin import OrderedTabularInline, OrderedInlineModelAdminMixin

from .models import Rule, Alternative, DiversityDimension, RuleDiversityDimension, Source, TrainingSentence

class CreatedByAdmin(admin.ModelAdmin):
    base_readonly_fields = ("created_by")

    def save_model(self, request, obj, form, change): 
        obj.createdby = request.user
        obj.save()

class AlternativeAdmin(CreatedByAdmin):
    class Meta:
        model = Alternative

    list_display = ('name', 'move_up_down_links')

class AlternativeInline(OrderedTabularInline):
    model = Alternative
    fields = ('lemma', 'word_types', 'is_singular', 'is_inspiration', 'is_active', 'label', 'source_text', 'source', 'comment', 'order', 'move_up_down_links',)
    readonly_fields = ('order', 'move_up_down_links',)
    ordering = ('order',)
    extra = 1

class TrainingSentenceInline(admin.TabularInline):
    model = TrainingSentence

class DiversityDimensionResource(resources.ModelResource):
    class Meta:
        model = DiversityDimension

class RuleDiversityDimensionInline(OrderedTabularInline):
    model = RuleDiversityDimension
    fields = ('diversity_dimension', 'order', 'move_up_down_links',)
    readonly_fields = ('order', 'move_up_down_links',)
    ordering = ('order',)
    extra = 1

@admin.register(DiversityDimension)
class DiversityDimensionAdmin(ImportExportModelAdmin):
    resource_class = DiversityDimensionResource

    class Meta:
        model = DiversityDimension

@admin.register(Rule)
class RuleAdmin(OrderedInlineModelAdminMixin, CreatedByAdmin):
    class Meta:
        model = Rule

    fields = ('language', 'lemma', 'word_types', 'is_inspiration', 'is_context_aware', 'is_active', 'label', 'source_text', 'source', 'comment', 'ownedby')

    inlines = [
        RuleDiversityDimensionInline,
        AlternativeInline,
        TrainingSentenceInline,
    ]

@admin.register(Source)
class SourceAdmin(CreatedByAdmin):
    class Meta:
        model = Source
