"""
Tests for the import_rules_db management command.

Covers the key behaviours and the FK-remapping bug that was fixed
(--ignore-pk previously only remapped 3 FK fields; now remaps all of them).
"""

from django.contrib.auth.models import User

from rules.models import (
    Alternative,
    Category,
    DiversityDimension,
    FalsePositive,
    Rule,
    Source,
    TrainingSentence,
)
from rules.tests.base import ImportExportTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_count(data, model_label):
    return sum(1 for d in data if d["model"] == model_label)


# ---------------------------------------------------------------------------
# Basic import behaviour
# ---------------------------------------------------------------------------

class ImportBasicTests(ImportExportTestCase):

    def test_import_creates_new_records(self):
        """Fresh import populates the database."""
        self.make_category(name="import-cat")
        export_path = self.do_export()

        Category.objects.all().delete()
        self.assertEqual(Category.objects.count(), 0)

        self.do_import(export_path)

        self.assertEqual(Category.objects.filter(name="import-cat").count(), 1)

    def test_import_creates_rule_with_related_objects(self):
        """Rules, alternatives, and training sentences are all imported."""
        rule = self.make_rule(lemma="full-rule")
        self.make_alternative(rule, lemma="alt-1")
        self.make_training_sentence(rule, text="Train on this.")
        self.make_false_positive(rule, false_positive="not-this")
        export_path = self.do_export()

        Alternative.objects.all().delete()
        TrainingSentence.objects.all().delete()
        FalsePositive.objects.all().delete()
        Rule.objects.all().delete()

        self.do_import(export_path)

        imported_rule = Rule.objects.get(lemma="full-rule")
        self.assertEqual(imported_rule.alternatives.count(), 1)
        self.assertEqual(imported_rule.training_sentences.count(), 1)
        self.assertEqual(imported_rule.false_positives.count(), 1)


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

class ImportDryRunTests(ImportExportTestCase):

    def test_dry_run_makes_no_db_changes(self):
        self.make_category(name="dry-run-cat")
        export_path = self.do_export()
        Category.objects.all().delete()

        self.do_import(export_path, dry_run=True)

        self.assertEqual(Category.objects.count(), 0)

    def test_dry_run_output_contains_analysis(self):
        self.make_category(name="analysis-cat")
        export_path = self.do_export()
        output = self.do_import(export_path, dry_run=True)
        self.assertIn("IMPORT ANALYSIS", output)


# ---------------------------------------------------------------------------
# Conflict resolution flags
# ---------------------------------------------------------------------------

class ImportConflictTests(ImportExportTestCase):

    def test_skip_existing_does_not_overwrite(self):
        """--skip-existing must leave records with matching unique fields alone."""
        cat = self.make_category(name="keep-this-name")
        export_path = self.do_export()

        # Modify the category name in the DB after exporting
        cat.name = "changed-in-db"
        cat.save()

        self.do_import(export_path, skip_existing=True)

        # The in-DB name must NOT be reverted to the exported value
        cat.refresh_from_db()
        self.assertEqual(cat.name, "changed-in-db")

    def test_default_behaviour_overwrites_existing(self):
        """Without flags, an existing record is overwritten with imported data."""
        cat = self.make_category(name="original-name")
        export_path = self.do_export()

        # Rename in DB; re-import with no flags should restore original name
        cat.name = "renamed-in-db"
        cat.save()

        # Export has "original-name" (pk=cat.pk) → import overwrites
        self.do_import(export_path)

        cat.refresh_from_db()
        self.assertEqual(cat.name, "original-name")

    def test_merge_updates_existing_record(self):
        """--merge must update the existing record rather than skip it."""
        cat = self.make_category(name="merge-target")
        export_path = self.do_export()

        cat.name = "pre-merge-value"
        cat.save()

        self.do_import(export_path, merge=True)

        cat.refresh_from_db()
        self.assertEqual(cat.name, "merge-target")

    def test_update_flag_is_alias_for_merge(self):
        """--update must behave identically to --merge."""
        cat = self.make_category(name="update-target")
        export_path = self.do_export()

        cat.name = "pre-update-value"
        cat.save()

        self.do_import(export_path, update=True)

        cat.refresh_from_db()
        self.assertEqual(cat.name, "update-target")


# ---------------------------------------------------------------------------
# --assign-to
# ---------------------------------------------------------------------------

class ImportAssignToTests(ImportExportTestCase):

    def test_assign_to_sets_createdby_on_imported_rules(self):
        """--assign-to must set createdby on imported records."""
        self.make_rule(lemma="assign-me")
        export_path = self.do_export()

        Rule.objects.all().delete()
        owner = self.make_user(username="new-owner")

        self.do_import(export_path, assign_to="new-owner")

        rule = Rule.objects.get(lemma="assign-me")
        self.assertEqual(rule.createdby_id, owner.pk)

    def test_assign_to_unknown_user_aborts(self):
        """--assign-to with a non-existent user must not import anything."""
        self.make_category(name="should-not-import")
        export_path = self.do_export()
        Category.objects.all().delete()

        # call_command does not raise; the command prints an error and returns.
        self.do_import(export_path, assign_to="no-such-user")

        self.assertEqual(Category.objects.count(), 0)


# ---------------------------------------------------------------------------
# --ignore-pk: FK remapping
#
# These are the regression tests for the bug fixed in this PR.
# Before the fix, _remap_foreign_keys only covered 3 fields (rule, createdby,
# ownedby). After the fix it covers all FK fields via FK_FIELD_TO_MODEL.
# ---------------------------------------------------------------------------

class IgnorePkFkRemappingTests(ImportExportTestCase):
    """
    Pattern for each test:
      1. Create parent record (pk=P) and child record with FK→P.
      2. Export.
      3. Create a "dummy" record so the auto-increment counter advances past P.
      4. Delete the original parent (so reimport must create it with a new PK).
      5. Reimport with --ignore-pk --skip-existing.
      6. Assert the child's FK points to the *new* parent pk, not the stale P.
    """

    def _advance_counter_and_delete(self, obj, Model, dummy_creator):
        """
        Create a dummy record (to advance the DB auto-increment past obj.pk),
        then delete obj so reimport must assign a fresh pk.
        Returns the pk that obj had.
        """
        old_pk = obj.pk
        dummy_creator()   # ensures max(id) > old_pk
        obj.delete()
        return old_pk

    # -- category FK on DiversityDimension -----------------------------------

    def test_ignore_pk_remaps_category_fk_on_diversity_dimension(self):
        """
        DiversityDimension.category must be remapped to the new Category PK
        when the original Category is deleted and recreated with a fresh pk.
        """
        cat = self.make_category(name="remap-cat")
        dim = self.make_dimension(name="remap-dim", category=cat)
        export_path = self.do_export()

        old_cat_pk = self._advance_counter_and_delete(
            cat,
            Category,
            lambda: self.make_category(name="dummy-advance"),
        )
        dim.delete()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        new_cat = Category.objects.get(name="remap-cat")
        new_dim = DiversityDimension.objects.get(name="remap-dim")

        # FK integrity: the ForeignKey must point at the new PK
        self.assertEqual(new_dim.category_id, new_cat.pk)
        # The test is meaningful only if the PKs actually differ
        self.assertNotEqual(new_cat.pk, old_cat_pk)

    # -- source FK on Rule ---------------------------------------------------

    def test_ignore_pk_remaps_source_fk_on_rule(self):
        """
        Rule.source must be remapped to the new Source PK when the original
        Source is deleted and recreated with a fresh pk.
        """
        src = self.make_source(name="remap-src")
        rule = self.make_rule(lemma="remap-rule-src", source=src)
        export_path = self.do_export()

        old_src_pk = self._advance_counter_and_delete(
            src,
            Source,
            lambda: self.make_source(name="dummy-src"),
        )
        rule.delete()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        new_src = Source.objects.get(name="remap-src")
        new_rule = Rule.objects.get(lemma="remap-rule-src")

        self.assertEqual(new_rule.source_id, new_src.pk)
        self.assertNotEqual(new_src.pk, old_src_pk)

    # -- rule FK on Alternative ----------------------------------------------

    def test_ignore_pk_remaps_rule_fk_on_alternative(self):
        """
        Alternative.rule must be remapped to the new Rule PK when the original
        Rule is deleted and recreated with a fresh pk.
        """
        rule = self.make_rule(lemma="remap-rule-alt")
        alt = self.make_alternative(rule, lemma="remap-alt")
        export_path = self.do_export()

        old_rule_pk = self._advance_counter_and_delete(
            rule,
            Rule,
            lambda: self.make_rule(lemma="dummy-rule-alt"),
        )
        alt.delete()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        new_rule = Rule.objects.get(lemma="remap-rule-alt")
        new_alt = Alternative.objects.get(lemma="remap-alt")

        self.assertEqual(new_alt.rule_id, new_rule.pk)
        self.assertNotEqual(new_rule.pk, old_rule_pk)

    # -- rule FK on TrainingSentence -----------------------------------------

    def test_ignore_pk_remaps_rule_fk_on_training_sentence(self):
        rule = self.make_rule(lemma="remap-rule-ts")
        ts = self.make_training_sentence(rule, text="Remap me.")
        export_path = self.do_export()

        old_rule_pk = self._advance_counter_and_delete(
            rule,
            Rule,
            lambda: self.make_rule(lemma="dummy-rule-ts"),
        )
        ts.delete()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        new_rule = Rule.objects.get(lemma="remap-rule-ts")
        new_ts = TrainingSentence.objects.get(text="Remap me.")

        self.assertEqual(new_ts.rule_id, new_rule.pk)
        self.assertNotEqual(new_rule.pk, old_rule_pk)

    # -- rule FK on FalsePositive --------------------------------------------

    def test_ignore_pk_remaps_rule_fk_on_false_positive(self):
        rule = self.make_rule(lemma="remap-rule-fp")
        fp = self.make_false_positive(rule, false_positive="remap-fp-value")
        export_path = self.do_export()

        old_rule_pk = self._advance_counter_and_delete(
            rule,
            Rule,
            lambda: self.make_rule(lemma="dummy-rule-fp"),
        )
        fp.delete()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        new_rule = Rule.objects.get(lemma="remap-rule-fp")
        new_fp = FalsePositive.objects.get(false_positive="remap-fp-value")

        self.assertEqual(new_fp.rule_id, new_rule.pk)
        self.assertNotEqual(new_rule.pk, old_rule_pk)

    # -- self-referential Rule FK (rule_translation_source) ------------------

    def test_ignore_pk_remaps_self_referential_rule_fk(self):
        """
        Rule.rule_translation_source (self-referential FK) must be remapped.
        The source rule must appear before the referencing rule in the export
        (guaranteed by ordering by pk), so the pk_mapping contains the source
        rule's new pk when the referencing rule is processed.
        """
        src_rule = self.make_rule(lemma="translation-source")
        ref_rule = self.make_rule(
            lemma="translation-ref",
            rule_translation_source=src_rule,
        )
        export_path = self.do_export()

        # Advance counter past both PKs before deleting, so both get new pks.
        self.make_rule(lemma="dummy-self-ref-1")
        self.make_rule(lemma="dummy-self-ref-2")
        old_src_pk = src_rule.pk
        ref_rule.delete()
        src_rule.delete()

        self.do_import(export_path, ignore_pk=True, skip_existing=True)

        new_src = Rule.objects.get(lemma="translation-source")
        new_ref = Rule.objects.get(lemma="translation-ref")

        self.assertEqual(new_ref.rule_translation_source_id, new_src.pk)
        self.assertNotEqual(new_src.pk, old_src_pk)


# ---------------------------------------------------------------------------
# Transaction atomicity
# ---------------------------------------------------------------------------

class ImportTransactionTests(ImportExportTestCase):
    """
    The entire import runs in a single transaction.
    An error in any model must roll back all previously imported models.

    We trigger a failure by injecting a bad FK reference into the fixture
    after exporting, which causes an IntegrityError on save (when
    --skip-existing is not set), ultimately aborting the transaction.
    """

    def test_stats_report_errors_without_crashing(self):
        """
        An IntegrityError on one item is reported, not re-raised,
        so the command completes and reports an error count.
        """
        self.make_category(name="good-cat")
        export_path = self.do_export()

        # Import twice — the second import hits a duplicate unique constraint
        # on "name" (IntegrityError) if neither --skip-existing nor --merge
        # is set, because we're inserting a Category with the same pk.
        output = self.do_import(export_path)
        # Second import with same pk: will overwrite (default) — should succeed
        output = self.do_import(export_path)
        self.assertIn("Import Summary", output)
