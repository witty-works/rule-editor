"""
Tests for the fail-safe behaviour of the import/export chain.

The common thread: when identity is ambiguous or a reference cannot be
resolved, the importer must refuse and roll back rather than guess. A wrong
guess corrupts rule data silently; a refusal costs one manual step.
"""

import json
from io import StringIO

from django.core.management import call_command

from rules.models import (
    Alternative,
    FalsePositive,
    Rule,
    RuleDiversityDimension,
    RuleStructureEvaluation,
    TrainingSentence,
)
from rules.tests.base import ImportExportTestCase


class NoneNaturalKeyTests(ImportExportTestCase):
    """word_types=None and pattern=None are the NORM for rules (any-reading
    rules such as 'guru' have no word type at all). Duplicate detection used
    to bail out on None and silently duplicate exactly those rules."""

    def test_ignore_pk_reimport_of_none_word_types_rule_is_idempotent(self):
        self.make_rule(lemma="none-key-rule", word_types=None, pattern=None)
        export_path = self.do_export()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        self.assertEqual(
            Rule.objects.filter(lemma="none-key-rule").count(),
            1,
            "re-import with --ignore-pk must not duplicate rules whose "
            "natural key contains None values",
        )

    def test_ignore_pk_distinguishes_sibling_with_pattern(self):
        """None handling must still tell apart siblings differing only in
        pattern (the sibling is a distinct rule, not a duplicate)."""
        self.make_rule(lemma="sibling-rule", word_types="n", pattern=None)
        export_path = self.do_export()

        data = self.load_export(export_path)
        for item in data:
            if item["model"] == "rules.rule":
                item["fields"]["pattern"] = "l|n"
                item["pk"] = 9999
        patched = self._tmp_path()
        patched.write_text(json.dumps(data))

        self.do_import(patched, ignore_pk=True, skip_existing=True)

        self.assertEqual(Rule.objects.filter(lemma="sibling-rule").count(), 2)


class UnmappedForeignKeyTests(ImportExportTestCase):
    """Under --ignore-pk a child whose parent record is absent from the file
    must be refused: keeping the source-side pk would attach it to whatever
    local record owns that number."""

    def _child_only_export(self):
        rule = self.make_rule(lemma="fk-victim")
        self.make_alternative(rule, lemma="orphan-alt")
        export_path = self.do_export()

        data = self.load_export(export_path)
        data = [item for item in data if item["model"] != "rules.rule"]
        child_only = self._tmp_path()
        child_only.write_text(json.dumps(data))
        return rule, child_only

    def test_child_without_rule_in_file_is_refused_and_rolled_back(self):
        rule, child_only = self._child_only_export()

        # An unrelated local rule now owns a pk; the orphan alternative's
        # rule pointer must not be allowed to land on any local rule.
        Alternative.objects.all().delete()

        with self.assertRaises(SystemExit):
            self.do_import(child_only, ignore_pk=True)

        self.assertEqual(
            Alternative.objects.count(),
            0,
            "refused orphan must not be attached to any local rule",
        )

    def test_allow_partial_commits_clean_records_but_reports(self):
        rule, child_only = self._child_only_export()
        Alternative.objects.all().delete()

        out = self.do_import(child_only, ignore_pk=True, allow_partial=True)

        self.assertEqual(Alternative.objects.count(), 0)
        self.assertIn("Refused", out)


class MergeForeignKeySafetyTests(ImportExportTestCase):
    """--merge used to assign raw pk ints to FK descriptors, turning every
    merge of a child record into an import error."""

    def test_merge_updates_child_record_with_fk_intact(self):
        rule = self.make_rule(lemma="merge-child-rule")
        sentence = self.make_training_sentence(rule, text="Merge sentence.")
        sentence.is_false_positive = True
        sentence.save()
        export_path = self.do_export()

        sentence.is_false_positive = False
        sentence.save()

        out = self.do_import(export_path, merge=True)

        sentence.refresh_from_db()
        self.assertTrue(sentence.is_false_positive)
        self.assertEqual(sentence.rule_id, rule.pk)
        self.assertNotIn("Error", out)


class RollbackTests(ImportExportTestCase):
    """A half-applied import is worse than none: errors roll everything back
    unless --allow-partial says otherwise."""

    def _export_with_poison_pill(self):
        self.make_category(name="clean-category")
        export_path = self.do_export()

        data = self.load_export(export_path)
        data.append(
            {
                "model": "rules.trainingsentence",
                "pk": 424242,
                "fields": {"rule": 424242, "text": "dangling"},
            }
        )
        poisoned = self._tmp_path()
        poisoned.write_text(json.dumps(data))
        return poisoned

    def test_error_rolls_back_entire_import(self):
        poisoned = self._export_with_poison_pill()
        self.make_category(name="pre-existing").delete()
        from rules.models import Category

        Category.objects.all().delete()

        with self.assertRaises(SystemExit):
            self.do_import(poisoned)

        self.assertEqual(
            Category.objects.filter(name="clean-category").count(),
            0,
            "an error elsewhere in the file must roll back every record",
        )

    def test_allow_partial_commits_clean_records(self):
        poisoned = self._export_with_poison_pill()
        from rules.models import Category

        Category.objects.all().delete()

        self.do_import(poisoned, allow_partial=True)

        self.assertEqual(Category.objects.filter(name="clean-category").count(), 1)


class ManyToManyStrippingTests(ImportExportTestCase):
    """links/sanctions serialize as raw pk lists that mean nothing elsewhere
    and were never applied on import; the export drops them so what does not
    travel is explicit."""

    def test_rule_fixture_contains_no_m2m_fields(self):
        rule_a = self.make_rule(lemma="linked-a")
        rule_b = self.make_rule(lemma="linked-b")
        rule_a.links.add(rule_b)
        export_path = self.do_export()

        for item in self.load_export(export_path):
            if item["model"] == "rules.rule":
                self.assertNotIn("links", item["fields"])
                self.assertNotIn("sanctions", item["fields"])
                self.assertNotIn("tags", item["fields"])


class DimensionLinkIdempotenceTests(ImportExportTestCase):
    def test_ignore_pk_reimport_does_not_duplicate_dimension_links(self):
        rule = self.make_rule(lemma="dim-linked")
        dimension = self.make_dimension(name="dim-idempotent")
        self.link_rule_to_dimension(rule, dimension)
        export_path = self.do_export()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        self.assertEqual(
            RuleDiversityDimension.objects.filter(rule=rule).count(), 1
        )


class NoNaturalKeyModelTests(ImportExportTestCase):
    """Models without natural keys (RuleStructureEvaluation) fall back to
    full-content comparison: identical re-imports stay idempotent, changed
    content on the same pk is a conflict."""

    def test_identical_reimport_is_skipped(self):
        rule = self.make_rule(lemma="rse-rule")
        RuleStructureEvaluation.objects.create(rule=rule)
        export_path = self.do_export()

        out = self.do_import(export_path)

        self.assertEqual(RuleStructureEvaluation.objects.count(), 1)
        self.assertIn("Import completed", out)

    def test_changed_content_on_same_pk_is_a_conflict(self):
        rule = self.make_rule(lemma="rse-conflict-rule")
        evaluation = RuleStructureEvaluation.objects.create(rule=rule)
        export_path = self.do_export()

        evaluation.rule_source_rule = "locally changed"
        evaluation.save()

        with self.assertRaises(SystemExit):
            self.do_import(export_path)

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.rule_source_rule, "locally changed")


class RuleOrderingTests(ImportExportTestCase):
    """Parents must import before children regardless of file order: FK
    validation and --ignore-pk remapping run strictly in sequence."""

    def test_child_before_parent_in_file_imports_cleanly(self):
        parent = self.make_rule(lemma="topo-parent")
        self.make_rule(lemma="topo-child", parent=parent)
        export_path = self.do_export()

        # Reverse the rule items so the child comes first in the file.
        data = self.load_export(export_path)
        rules = [item for item in data if item["model"] == "rules.rule"]
        others = [item for item in data if item["model"] != "rules.rule"]
        reordered = self._tmp_path()
        reordered.write_text(json.dumps(others + rules[::-1]))

        Rule.objects.all().delete()

        self.do_import(reordered, ignore_pk=True)

        child = Rule.objects.get(lemma="topo-child")
        self.assertIsNotNone(child.parent)
        self.assertEqual(child.parent.lemma, "topo-parent")


class SingleRuleImportTests(ImportExportTestCase):
    """import_rule / export_rule: the edge-submission path."""

    def do_export_rule(self, rule, full=False):
        path = self._tmp_path()
        call_command(
            "export_rule",
            id=str(rule.pk),
            output=str(path),
            full=full,
            stdout=StringIO(),
            stderr=StringIO(),
        )
        return path

    def do_import_rule(self, path, **options):
        out = StringIO()
        call_command(
            "import_rule",
            input=str(path),
            stdout=out,
            stderr=StringIO(),
            **options,
        )
        return out.getvalue()

    def test_existing_rule_is_not_silently_replaced(self):
        """The old default deleted the local rule (cascading to all its
        children) and recreated it from the file. Default is now skip."""
        rule = self.make_rule(lemma="precious")
        local_sentence = self.make_training_sentence(rule, text="Local work.")
        export_path = self.do_export_rule(rule)

        self.do_import_rule(export_path)

        rule.refresh_from_db()
        self.assertTrue(
            TrainingSentence.objects.filter(pk=local_sentence.pk).exists(),
            "default import must not cascade-delete local children",
        )

    def test_replace_flag_replaces_explicitly(self):
        rule = self.make_rule(lemma="replace-me")
        export_path = self.do_export_rule(rule)
        local_sentence = self.make_training_sentence(rule, text="Doomed.")

        self.do_import_rule(export_path, replace=True)

        self.assertFalse(
            TrainingSentence.objects.filter(pk=local_sentence.pk).exists()
        )
        self.assertEqual(Rule.objects.filter(lemma="replace-me").count(), 1)

    def test_sibling_with_different_pattern_is_not_misdetected(self):
        """Identity uses the full natural key: a rule that differs only in
        pattern is a sibling, not the same rule."""
        with_pattern = self.make_rule(lemma="patterned", pattern="l|n")
        export_path = self.do_export_rule(with_pattern)

        with_pattern.delete()
        self.make_rule(lemma="patterned", pattern=None)

        self.do_import_rule(export_path)

        self.assertEqual(Rule.objects.filter(lemma="patterned").count(), 2)

    def test_reimport_does_not_duplicate_children(self):
        rule = self.make_rule(lemma="idempotent-children")
        self.make_alternative(rule, lemma="alt-1")
        self.make_training_sentence(rule, text="Sentence one.")
        self.make_false_positive(rule, false_positive="fp one")
        export_path = self.do_export_rule(rule)

        self.do_import_rule(export_path)
        self.do_import_rule(export_path)

        self.assertEqual(Alternative.objects.filter(rule=rule).count(), 1)
        self.assertEqual(TrainingSentence.objects.filter(rule=rule).count(), 1)
        self.assertEqual(FalsePositive.objects.filter(rule=rule).count(), 1)

    def test_dimension_link_lands_on_recreated_dimension(self):
        """Regression: the FK label for diversity_dimension was derived from
        the field name and never matched, so links kept source-side pks."""
        rule = self.make_rule(lemma="dim-remap")
        dimension = self.make_dimension(name="dim-remap-target")
        self.link_rule_to_dimension(rule, dimension)
        export_path = self.do_export_rule(rule, full=True)

        RuleDiversityDimension.objects.all().delete()
        rule.delete()
        dimension.delete()

        self.do_import_rule(export_path, create_dependencies=True)

        new_rule = Rule.objects.get(lemma="dim-remap")
        link = RuleDiversityDimension.objects.get(rule=new_rule)
        self.assertEqual(link.diversity_dimension.name, "dim-remap-target")

    def test_parent_precedes_child_in_export_and_import(self):
        parent = self.make_rule(lemma="the-parent")
        child = self.make_rule(lemma="the-child", parent=parent)
        export_path = self.do_export_rule(child)

        child.delete()
        parent.delete()

        self.do_import_rule(export_path)

        new_child = Rule.objects.get(lemma="the-child")
        self.assertIsNotNone(new_child.parent)
        self.assertEqual(new_child.parent.lemma, "the-parent")

    def test_child_with_unimported_rule_is_an_error_not_a_misattachment(self):
        rule = self.make_rule(lemma="orphan-source")
        self.make_alternative(rule, lemma="orphan-alt-single")
        export_path = self.do_export_rule(rule)

        data = self.load_export(export_path)
        data = [item for item in data if item["model"] != "rules.rule"]
        child_only = self._tmp_path()
        child_only.write_text(json.dumps(data))

        bystander = self.make_rule(lemma="bystander")
        before = Alternative.objects.filter(rule=bystander).count()

        with self.assertRaises(SystemExit):
            self.do_import_rule(child_only)

        self.assertEqual(
            Alternative.objects.filter(rule=bystander).count(), before
        )
        self.assertFalse(
            Alternative.objects.filter(lemma="orphan-alt-single")
            .exclude(rule=rule)
            .exists()
        )
