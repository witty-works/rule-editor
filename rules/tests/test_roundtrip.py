"""
End-to-end roundtrip tests for the import/export system.

These tests verify that data exported from the DB can be imported back
faithfully — with and without --ignore-pk — and that FK integrity is
maintained throughout the full cycle.
"""

from rules.models import (
    Alternative,
    Category,
    DiversityDimension,
    FalsePositive,
    Rule,
    RuleDiversityDimension,
    Source,
    TrainingSentence,
)
from rules.tests.base import ImportExportTestCase


class RoundtripCountTests(ImportExportTestCase):
    """Export → wipe → import must restore the same record counts."""

    def _counts(self):
        return {
            "categories": Category.objects.count(),
            "dimensions": DiversityDimension.objects.count(),
            "rules": Rule.objects.count(),
            "alternatives": Alternative.objects.count(),
            "training_sentences": TrainingSentence.objects.count(),
            "false_positives": FalsePositive.objects.count(),
        }

    def _wipe_all(self):
        FalsePositive.objects.all().delete()
        TrainingSentence.objects.all().delete()
        Alternative.objects.all().delete()
        RuleDiversityDimension.objects.all().delete()
        Rule.objects.all().delete()
        DiversityDimension.objects.all().delete()
        Category.objects.all().delete()
        Source.objects.all().delete()

    def test_roundtrip_empty_db(self):
        """Exporting an empty DB produces an import that keeps the DB empty."""
        export_path = self.do_export()
        self.do_import(export_path)
        self.assertEqual(self._counts(), {k: 0 for k in self._counts()})

    def test_roundtrip_preserves_record_counts(self):
        """All created records survive a full export → wipe → import cycle."""
        cat = self.make_category(name="roundtrip-cat")
        dim = self.make_dimension(name="roundtrip-dim", category=cat)
        rule = self.make_rule(lemma="roundtrip-rule")
        self.make_alternative(rule, lemma="roundtrip-alt")
        self.make_training_sentence(rule, text="Roundtrip sentence.")
        self.make_false_positive(rule, false_positive="roundtrip-fp")
        self.link_rule_to_dimension(rule, dim)

        before = self._counts()
        export_path = self.do_export()
        self._wipe_all()

        self.do_import(export_path)

        self.assertEqual(self._counts(), before)

    def test_roundtrip_preserves_field_values(self):
        """Specific field values survive export → import unchanged."""
        cat = self.make_category(name="field-value-cat")
        rule = self.make_rule(lemma="field-value-rule", language="de")
        alt = self.make_alternative(rule, lemma="field-value-alt", order=42)

        export_path = self.do_export()
        self._wipe_all()
        self.do_import(export_path)

        self.assertTrue(Category.objects.filter(name="field-value-cat").exists())
        imported_rule = Rule.objects.get(lemma="field-value-rule")
        self.assertEqual(imported_rule.language, "de")
        imported_alt = Alternative.objects.get(lemma="field-value-alt")
        self.assertEqual(imported_alt.order, 42)

    def test_roundtrip_compressed(self):
        """Gzip-compressed export → import produces the same records."""
        self.make_category(name="gz-roundtrip-cat")
        self.make_rule(lemma="gz-roundtrip-rule")

        before = self._counts()
        export_path = self.do_export(suffix=".json.gz")
        self._wipe_all()

        self.do_import(export_path)

        self.assertEqual(self._counts(), before)


class RoundtripFkIntegrityTests(ImportExportTestCase):
    """
    FK relationships must be preserved after a roundtrip, even when PKs change
    (--ignore-pk mode).  These tests verify the fix to _remap_foreign_keys.
    """

    def _wipe_all(self):
        FalsePositive.objects.all().delete()
        TrainingSentence.objects.all().delete()
        Alternative.objects.all().delete()
        RuleDiversityDimension.objects.all().delete()
        Rule.objects.all().delete()
        DiversityDimension.objects.all().delete()
        Category.objects.all().delete()
        Source.objects.all().delete()

    def test_rule_dimension_link_survives_ignore_pk_roundtrip(self):
        """
        The Rule ↔ DiversityDimension through-model must be rebuilt correctly
        so rule.diversity_dimensions still returns the same dimension by name.
        """
        cat = self.make_category(name="link-cat")
        dim = self.make_dimension(name="link-dim", category=cat)
        rule = self.make_rule(lemma="link-rule")
        self.link_rule_to_dimension(rule, dim)

        export_path = self.do_export()
        self._wipe_all()

        # Advance auto-increment so reimported records get different PKs
        dummy_cat = self.make_category(name="pk-advance-cat")

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        reimported_rule = Rule.objects.get(lemma="link-rule")
        dim_names = list(
            reimported_rule.diversity_dimensions.values_list("name", flat=True)
        )
        self.assertIn("link-dim", dim_names)

        # DiversityDimension.category must also be correctly remapped
        reimported_dim = DiversityDimension.objects.get(name="link-dim")
        self.assertEqual(reimported_dim.category.name, "link-cat")

    def test_alternative_rule_fk_correct_after_ignore_pk_roundtrip(self):
        """Alternative.rule must resolve to the correct Rule after reimport."""
        rule = self.make_rule(lemma="fk-check-rule")
        alt = self.make_alternative(rule, lemma="fk-check-alt")

        export_path = self.do_export()
        self._wipe_all()
        self.make_rule(lemma="pk-advance-dummy")  # advance counter

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        reimported_alt = Alternative.objects.get(lemma="fk-check-alt")
        self.assertEqual(reimported_alt.rule.lemma, "fk-check-rule")

    def test_source_fk_on_rule_correct_after_ignore_pk_roundtrip(self):
        """Rule.source must resolve to the correct Source after reimport."""
        src = self.make_source(name="fk-src")
        rule = self.make_rule(lemma="fk-src-rule", source=src)

        export_path = self.do_export()
        self._wipe_all()
        self.make_source(name="pk-advance-src")  # advance counter

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        reimported_rule = Rule.objects.get(lemma="fk-src-rule")
        self.assertEqual(reimported_rule.source.name, "fk-src")

    def test_user_refs_are_null_after_roundtrip(self):
        """
        createdby / ownedby must always be null after an export → import cycle
        because the exporter strips them (privacy guarantee).
        """
        user = self.make_user()
        rule = self.make_rule(lemma="user-ref-rule")
        rule.createdby = user
        rule.ownedby = user
        rule.save()

        export_path = self.do_export()
        rule.delete()

        self.do_import(export_path)

        reimported = Rule.objects.get(lemma="user-ref-rule")
        self.assertIsNone(reimported.createdby_id)
        self.assertIsNone(reimported.ownedby_id)
