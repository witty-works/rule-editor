"""
Tests for the export_rules_db management command.

Each test creates a known DB state, runs the command, and asserts on the
resulting JSON file — structure, content, and filtering behaviour.
"""

import json

from rules.models import (
    Category,
    DiversityDimension,
    Rule,
    RuleDiversityDimension,
)
from rules.tests.base import ImportExportTestCase


class ExportStructureTests(ImportExportTestCase):
    """The exported file must always be a valid JSON array of fixture dicts."""

    def test_export_empty_db_produces_empty_array(self):
        path = self.do_export()
        data = self.load_export(path)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_export_produces_fixture_schema(self):
        """Every object in the export must have model / pk / fields keys."""
        self.make_category(name="schema-cat")
        path = self.do_export()
        data = self.load_export(path)
        self.assertGreater(len(data), 0)
        for item in data:
            self.assertIn("model", item)
            self.assertIn("pk", item)
            self.assertIn("fields", item)

    def test_export_compressed_roundtrip(self):
        """.json.gz output can be loaded back."""
        self.make_category(name="gz-cat")
        path = self.do_export(suffix=".json.gz")
        self.assertTrue(str(path).endswith(".json.gz"))
        data = self.load_export(path)
        models = [item["model"] for item in data]
        self.assertIn("rules.category", models)


class ExportPrivacyTests(ImportExportTestCase):
    """User references must be stripped from the export."""

    def test_createdby_is_null(self):
        user = self.make_user()
        cat = self.make_category(name="owned-cat")
        cat.createdby = user
        cat.save()

        path = self.do_export()
        data = self.load_export(path)

        cat_items = [d for d in data if d["model"] == "rules.category"]
        self.assertTrue(cat_items, "Category not in export")
        for item in cat_items:
            self.assertIsNone(item["fields"].get("createdby"))

    def test_ownedby_is_null(self):
        user = self.make_user()
        rule = self.make_rule(lemma="owned-rule")
        rule.ownedby = user
        rule.save()

        path = self.do_export()
        data = self.load_export(path)

        rule_items = [d for d in data if d["model"] == "rules.rule"]
        self.assertTrue(rule_items, "Rule not in export")
        for item in rule_items:
            self.assertIsNone(item["fields"].get("ownedby"))

    def test_no_auth_user_records_exported(self):
        """auth.user records must never appear in the export."""
        self.make_user()
        path = self.do_export()
        data = self.load_export(path)
        user_items = [d for d in data if d["model"].startswith("auth.")]
        self.assertEqual(user_items, [])


class ExportFilterTests(ImportExportTestCase):
    """Filters narrow the export to matching rules and their related objects."""

    def _make_rule_with_dimension(self, lemma, language, dim_name):
        cat = self.make_category(name=f"cat-for-{dim_name}")
        dim = self.make_dimension(name=dim_name, category=cat)
        rule = self.make_rule(lemma=lemma, language=language)
        self.link_rule_to_dimension(rule, dim)
        return rule, dim

    def test_language_filter_excludes_other_languages(self):
        rule_en = self.make_rule(lemma="en-rule", language="en")
        rule_de = self.make_rule(lemma="de-rule", language="de")

        path = self.do_export(language="en")
        data = self.load_export(path)
        exported_pks = {
            d["pk"] for d in data if d["model"] == "rules.rule"
        }

        self.assertIn(rule_en.pk, exported_pks)
        self.assertNotIn(rule_de.pk, exported_pks)

    def test_rule_ids_filter_exports_only_specified_rules(self):
        rule_a = self.make_rule(lemma="rule-a")
        rule_b = self.make_rule(lemma="rule-b")

        path = self.do_export(rule_ids=str(rule_a.pk))
        data = self.load_export(path)
        exported_pks = {d["pk"] for d in data if d["model"] == "rules.rule"}

        self.assertIn(rule_a.pk, exported_pks)
        self.assertNotIn(rule_b.pk, exported_pks)

    def test_related_objects_match_rule_filter(self):
        """Alternatives and training sentences follow the rule filter."""
        rule_a = self.make_rule(lemma="filtered-rule")
        rule_b = self.make_rule(lemma="other-rule")
        alt_a = self.make_alternative(rule_a, lemma="alt-for-a")
        alt_b = self.make_alternative(rule_b, lemma="alt-for-b")

        path = self.do_export(rule_ids=str(rule_a.pk))
        data = self.load_export(path)
        exported_alt_pks = {d["pk"] for d in data if d["model"] == "rules.alternative"}

        self.assertIn(alt_a.pk, exported_alt_pks)
        self.assertNotIn(alt_b.pk, exported_alt_pks)

    def test_exclude_linguistic_data_omits_noun_verb_models(self):
        path = self.do_export(exclude_linguistic_data=True)
        data = self.load_export(path)
        linguistic_models = {d["model"] for d in data}
        for model in [
            "rules.englishnoun",
            "rules.englishverb",
            "rules.germannoun",
            "rules.frenchnoun",
        ]:
            self.assertNotIn(model, linguistic_models)

    def test_dimension_filter_exports_only_matching_rules(self):
        rule_gender, dim = self._make_rule_with_dimension(
            "gender-rule", "en", "gender"
        )
        rule_age, _ = self._make_rule_with_dimension("age-rule", "en", "age")

        path = self.do_export(dimension="gender")
        data = self.load_export(path)
        exported_rule_pks = {d["pk"] for d in data if d["model"] == "rules.rule"}

        self.assertIn(rule_gender.pk, exported_rule_pks)
        self.assertNotIn(rule_age.pk, exported_rule_pks)
