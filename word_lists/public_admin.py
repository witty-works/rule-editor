from public_admin.admin import PublicModelAdmin
from public_admin.sites import PublicAdminSite, PublicApp

from rules.models import (
    GermanVerb,
    GermanAdjective,
    GermanNoun,
    EnglishVerb,
    EnglishAdjective,
    EnglishNoun,
)

# TODO https://github.com/django-import-export/django-import-export/issues/1725
from import_export import resources
from import_export.admin import ExportMixin


class EnglishVerbResource(resources.ModelResource):
    class Meta:
        model = EnglishVerb


class EnglishVerbAdmin(ExportMixin, PublicModelAdmin):
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


class EnglishAdjectiveAdmin(ExportMixin, PublicModelAdmin):
    resource_class = EnglishAdjectiveResource

    search_fields = ("base_form", "comparative", "superlative")
    fields = ("base_form", "comparative", "superlative", "is_absolute")
    list_filter = ("is_absolute",)
    list_display = ("base_form", "comparative", "superlative", "is_absolute")


class EnglishNounResource(resources.ModelResource):
    class Meta:
        model = EnglishNoun


class EnglishNounAdmin(ExportMixin, PublicModelAdmin):
    resource_class = EnglishNounResource

    search_fields = ("base_form", "plural")
    fields = ("base_form", "plural")
    list_display = (
        "base_form",
        "plural",
    )


class GermanVerbResource(resources.ModelResource):
    class Meta:
        model = GermanVerb


class GermanVerbAdmin(ExportMixin, PublicModelAdmin):
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
    )
    list_filter = ("helping_verb",)
    list_display = ("base_form", "past_participle", "helping_verb", "infinitiv_zu")


class GermanAdjectiveResource(resources.ModelResource):
    class Meta:
        model = GermanAdjective


class GermanAdjectiveAdmin(ExportMixin, PublicModelAdmin):
    resource_class = GermanAdjectiveResource

    search_fields = ("base_form", "comparative", "superlative")
    fields = ("base_form", "comparative", "superlative", "is_absolute")
    list_filter = ("is_absolute",)
    list_display = ("base_form", "comparative", "superlative", "is_absolute")


class GermanNounResource(resources.ModelResource):
    class Meta:
        model = GermanNoun


class GermanNounAdmin(ExportMixin, PublicModelAdmin):
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
    )
    list_filter = (
        "gender_1",
        "gender_2",
        "singular_only",
        "plural_only",
    )
    list_display = ("base_form", "female_form", "male_form", "gender_1")


public_app = PublicApp(
    "rules",
    models=(
        "GermanVerb",
        "GermanAdjective",
        "GermanNoun",
        "EnglishVerb",
        "EnglishAdjective",
        "EnglishNoun",
    ),
)
public_admin = PublicAdminSite("word_lists", public_app)
public_admin.register(GermanVerb, GermanVerbAdmin)
public_admin.register(GermanAdjective, GermanAdjectiveAdmin)
public_admin.register(GermanNoun, GermanNounAdmin)
public_admin.register(EnglishVerb, EnglishVerbAdmin)
public_admin.register(EnglishAdjective, EnglishAdjectiveAdmin)
public_admin.register(EnglishNoun, EnglishNounAdmin)
