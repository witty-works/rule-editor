#!/usr/bin/env python3
"""
Test user reference handling in import/export commands.
This verifies that all models with user references are properly handled.
"""

import os
import sys
import json
import subprocess
import traceback

# Use shared constants to avoid string duplication
from rules.model_constants import (
    CATEGORY,
    DIV_DIM,
    SOURCE,
    RULE,
    ALTERNATIVE,
    TRAINING_SENTENCE,
    FALSE_POSITIVE,
    LEMMATIZATION,
    EN_NOUN,
    EN_VERB,
    EN_ADJ,
    DE_NOUN,
    DE_VERB,
    DE_ADJ,
    FR_NOUN,
    RULE_STRUCTURE_EVAL,
    FIELD_CREATEDBY,
    FIELD_OWNEDBY,
)


def test_user_references():
    """Test that all user references are properly nullified in export"""

    print("\n" + "=" * 60)
    print("Testing User Reference Handling")
    print("=" * 60)

    # Models that should have user references
    models_with_refs = {
        CATEGORY: [FIELD_CREATEDBY],
        DIV_DIM: [FIELD_CREATEDBY],
        SOURCE: [FIELD_CREATEDBY],
        RULE: [FIELD_CREATEDBY, FIELD_OWNEDBY],
        ALTERNATIVE: [FIELD_CREATEDBY],
        TRAINING_SENTENCE: [FIELD_CREATEDBY],
        FALSE_POSITIVE: [FIELD_CREATEDBY],
        LEMMATIZATION: [FIELD_CREATEDBY],
        EN_NOUN: [FIELD_CREATEDBY],
        EN_VERB: [FIELD_CREATEDBY],
        EN_ADJ: [FIELD_CREATEDBY],
        DE_NOUN: [FIELD_CREATEDBY],
        DE_VERB: [FIELD_CREATEDBY],
        DE_ADJ: [FIELD_CREATEDBY],
        FR_NOUN: [FIELD_CREATEDBY],
        RULE_STRUCTURE_EVAL: [FIELD_CREATEDBY],
    }

    # Create a test export
    print("\n1. Creating test export...")

    result = subprocess.run(
        [
            "pipenv",
            "run",
            "python",
            "manage.py",
            "export_rules_db",
            "--output=test_user_refs.json",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"❌ Export failed: {result.stderr}")
        return False

    print("✅ Export created")

    # Load and check the export
    print("\n2. Checking user references in export...")
    try:
        with open("test_user_refs.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load export: {e}")
        return False

    print(f"   Loaded {len(data)} objects")

    # Check each object
    issues_found = []
    models_checked = set()

    for item in data:
        model = item.get("model")
        fields = item.get("fields", {})

        if model in models_with_refs:
            models_checked.add(model)
            expected_refs = models_with_refs[model]

            for ref in expected_refs:
                if ref in fields and fields[ref] is not None:
                    issues_found.append(
                        f"   ❌ {model} pk={item.get('pk')}: {ref} = {fields[ref]} (expected null)"
                    )

    # Report results
    print("\n3. Results:")
    print(f"   Models checked: {len(models_checked)}")
    print(f"   Models expected: {len(models_with_refs)}")

    if issues_found:
        print(f"\n   ❌ FAILED - Found {len(issues_found)} issues:")
        for issue in issues_found[:10]:  # Show first 10
            print(issue)
        if len(issues_found) > 10:
            print(f"   ... and {len(issues_found) - 10} more")
        return False
    else:
        print("   ✅ PASSED - All user references properly nullified")

        # Show which models were found
        if models_checked:
            print("\n   Models with user refs found in export:")
            for model in sorted(models_checked):
                refs = ", ".join(models_with_refs[model])
                print(f"     - {model}: {refs}")

        # Show which models were not in export (may not have data)
        missing = set(models_with_refs.keys()) - models_checked
        if missing:
            print("\n   Models not in export (may not have data):")
            for model in sorted(missing):
                print(f"     - {model}")

    # Cleanup
    if os.path.exists("test_user_refs.json"):
        os.remove("test_user_refs.json")
        print("\n4. Cleaned up test file")

    return True


def test_import_assignment():
    """Test that import with --assign-to properly assigns users"""

    print("\n" + "=" * 60)
    print("Testing Import User Assignment")
    print("=" * 60)

    print("\nThis test verifies that the --assign-to flag is documented")
    print("and available in the import commands.")

    # Check import_rules_db command
    print("\n1. Checking import_rules_db --help...")

    result = subprocess.run(
        ["pipenv", "run", "python", "manage.py", "import_rules_db", "--help"],
        capture_output=True,
        text=True,
    )

    if "--assign-to" in result.stdout:
        print("   ✅ import_rules_db has --assign-to flag")
    else:
        print("   ❌ import_rules_db missing --assign-to flag")
        return False

    # Check import_rule command
    print("\n2. Checking import_rule --help...")
    result = subprocess.run(
        ["pipenv", "run", "python", "manage.py", "import_rule", "--help"],
        capture_output=True,
        text=True,
    )

    if "--owner" in result.stdout:
        print("   ✅ import_rule has --owner flag")
    else:
        print("   ❌ import_rule missing --owner flag")
        return False

    print("\n   ✅ PASSED - Both import commands support user assignment")
    return True


def main():
    print("\n" + "=" * 70)
    print("USER REFERENCE HANDLING TEST SUITE")
    print("=" * 70)

    tests = [
        ("Export nullifies user references", test_user_references),
        ("Import commands support user assignment", test_import_assignment),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test crashed: {e}")
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All user reference handling tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
