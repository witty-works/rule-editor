"""
Shared base class and factory helpers for import/export tests.

BaseLemmaModel.clean() calls an external NLP API (tokenize + parse_word_types).
We mock both on the class so every test that creates a Rule or Alternative
works without a live NLP service, while still exercising the rest of the
model's clean() logic.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from rules.models import (
    Alternative,
    BaseLemmaModel,
    Category,
    DiversityDimension,
    FalsePositive,
    Rule,
    RuleDiversityDimension,
    Source,
    TrainingSentence,
)


class ImportExportTestCase(TestCase):
    """
    Base for all import/export tests.

    Sets up NLP mocks and provides:
      - Factory methods (make_*) that create minimally valid DB records.
      - do_export / do_import helpers that call the management commands via
        call_command (in-process, no subprocess), writing to temp files that
        are cleaned up automatically at the end of each test.
    """

    def setUp(self):
        super().setUp()

        # Fake tokenize: returns one token, matching the "default" rule type.
        self.tokenize_patcher = mock.patch.object(
            BaseLemmaModel, "tokenize", return_value=(["token"], ["token"], "")
        )
        # Fake parse_word_types: returns an empty dict (no word-type constraint).
        self.parse_patcher = mock.patch.object(
            BaseLemmaModel, "parse_word_types", return_value={}
        )
        self.tokenize_patcher.start()
        self.parse_patcher.start()
        self.addCleanup(self.tokenize_patcher.stop)
        self.addCleanup(self.parse_patcher.stop)

        self._tmp_files = []

    def tearDown(self):
        for path in self._tmp_files:
            path.unlink(missing_ok=True)
        super().tearDown()

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    def make_category(self, name=None, **kwargs):
        name = name or f"cat-{id(self)}-{Category.objects.count()}"
        return Category.objects.create(name=name, **kwargs)

    def make_dimension(self, name=None, category=None, **kwargs):
        n = DiversityDimension.objects.count()
        return DiversityDimension.objects.create(
            name=name or f"dim-{id(self)}-{n}",
            parent_name=f"parent-{n}",
            category=category or self.make_category(),
            proficiency_level="inclusive",
            **kwargs,
        )

    def make_source(self, name=None, **kwargs):
        n = Source.objects.count()
        return Source.objects.create(name=name or f"src-{id(self)}-{n}", **kwargs)

    def make_rule(self, lemma=None, language="en", **kwargs):
        n = Rule.objects.count()
        return Rule.objects.create(
            lemma=lemma or f"lemma-{id(self)}-{n}",
            text_id=f"text-id-{id(self)}-{n}",
            language=language,
            **kwargs,
        )

    def make_alternative(self, rule, lemma=None, order=None):
        n = Alternative.objects.count()
        return Alternative.objects.create(
            rule=rule,
            lemma=lemma or f"alt-{id(self)}-{n}",
            order=order if order is not None else n + 1,
        )

    def make_training_sentence(self, rule, text="A test sentence."):
        return TrainingSentence.objects.create(rule=rule, text=text)

    def make_false_positive(self, rule, false_positive=None):
        n = FalsePositive.objects.count()
        return FalsePositive.objects.create(
            rule=rule,
            false_positive=false_positive or f"fp-{id(self)}-{n}",
        )

    def make_user(self, username=None, **kwargs):
        n = User.objects.count()
        return User.objects.create_user(
            username=username or f"user-{id(self)}-{n}",
            password="test-password",
            **kwargs,
        )

    def link_rule_to_dimension(self, rule, dimension, order=1):
        return RuleDiversityDimension.objects.create(
            rule=rule,
            diversity_dimension=dimension,
            order=order,
        )

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------

    def _tmp_path(self, suffix=".json"):
        path = Path(tempfile.mktemp(suffix=suffix))
        self._tmp_files.append(path)
        return path

    def do_export(self, suffix=".json", **options):
        """
        Run export_rules_db and return the Path of the written file.
        All keyword arguments are forwarded to call_command.
        """
        path = self._tmp_path(suffix=suffix)
        call_command(
            "export_rules_db",
            output=str(path),
            stdout=StringIO(),
            stderr=StringIO(),
            **options,
        )
        return path

    def do_import(self, path, **options):
        """
        Run import_rules_db against *path* and return captured stdout.
        All keyword arguments are forwarded to call_command.
        """
        out = StringIO()
        call_command(
            "import_rules_db",
            input=str(path),
            stdout=out,
            stderr=StringIO(),
            **options,
        )
        return out.getvalue()

    def load_export(self, path):
        """Return the deserialized list from an export file."""
        if str(path).endswith(".gz"):
            import gzip

            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(path.read_text(encoding="utf-8"))
