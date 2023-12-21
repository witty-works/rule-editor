from dal import autocomplete

from taggit.models import Tag
from rules.models import DiversityDimension, Rule
from django.db.models import Q


class TagAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return Tag.objects.none()

        qs = Tag.objects.all()

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs

    def get_create_option(self, context, q):
        return []


class DiversityDimensionAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return DiversityDimension.objects.none()

        qs = DiversityDimension.objects.all()

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs

    def get_create_option(self, context, q):
        return []


class RuleAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return Rule.objects.none()

        qs = Rule.objects.all()

        ignore_id = self.forwarded.get("ignore_id", None)
        if ignore_id:
            qs = qs.filter(~Q(id=ignore_id))

        language = self.forwarded.get("language", None)
        if language:
            qs = qs.filter(language=language)

        if self.q:
            qs = qs.filter(lemma__istartswith=self.q)

        return qs

    def get_create_option(self, context, q):
        return []
