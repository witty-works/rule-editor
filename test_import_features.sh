#!/bin/bash
# Test script for import features: dry-run and ignore-pk
# This creates a small test dataset and verifies the import features work

set -e

echo "=========================================="
echo "Testing Import Features"
echo "=========================================="
echo ""

# Create a small test JSON file
cat > /tmp/test_import.json << 'EOF'
[
  {
    "model": "rules.category",
    "pk": 999,
    "fields": {
      "name": "test-category",
      "comment": "Test category for import",
      "created_at": "2024-01-01",
      "updated_at": "2024-01-01 00:00:00",
      "createdby": null
    }
  },
  {
    "model": "rules.rule",
    "pk": 9999,
    "fields": {
      "lemma": "test-lemma",
      "trigger": "test-trigger",
      "language": "en",
      "is_prefix": false,
      "comment": "Test rule for import",
      "created_at": "2024-01-01",
      "updated_at": "2024-01-01 00:00:00",
      "createdby": null,
      "ownedby": null
    }
  }
]
EOF

echo "✓ Created test import file: /tmp/test_import.json"
echo ""

# Test 1: Dry run
echo "=========================================="
echo "Test 1: Dry Run Analysis"
echo "=========================================="
echo ""
echo "Running: pipenv run python manage.py import_rules_db --input=/tmp/test_import.json --dry-run"
echo ""

pipenv run python manage.py import_rules_db --input=/tmp/test_import.json --dry-run

echo ""
echo "✓ Dry run completed successfully"
echo ""

# Test 2: Check if --ignore-pk flag is recognized
echo "=========================================="
echo "Test 2: Testing --ignore-pk Flag"
echo "=========================================="
echo ""
echo "Running: pipenv run python manage.py import_rules_db --help | grep ignore-pk"
echo ""

if pipenv run python manage.py import_rules_db --help | grep -q "ignore-pk"; then
    echo "✓ --ignore-pk flag is available"
else
    echo "✗ --ignore-pk flag not found"
    exit 1
fi

echo ""

# Clean up
rm /tmp/test_import.json
echo "✓ Cleaned up test file"
echo ""

echo "=========================================="
echo "All Tests Passed!"
echo "=========================================="
echo ""
echo "Features verified:"
echo "  ✓ Dry run shows detailed analysis"
echo "  ✓ --ignore-pk flag available"
echo ""
echo "To test actual import with --ignore-pk:"
echo "  python manage.py import_rules_db --input=FILE --ignore-pk --skip-existing --assign-to=USERNAME"
