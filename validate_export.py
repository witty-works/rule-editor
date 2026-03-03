#!/usr/bin/env python3
"""
Validate a rules export JSON file against the schema.
Usage: python validate_export.py <export_file.json> or <export_file.json.gz>
"""

import gzip
import json
import sys
from pathlib import Path
from collections import Counter
import jsonschema  # Dependency assumed present

# Simple constants to reduce duplication
USAGE = "Usage: python validate_export.py <export_file.json> or <export_file.json.gz>"
SCHEMA_PATH_DEFAULT = "schemas/rules_export_schema.json"


def validate_export(export_file, schema_file=SCHEMA_PATH_DEFAULT):
    """Validate an export file against the JSON schema."""

    # Load schema
    schema_path = Path(__file__).parent / schema_file
    if not schema_path.exists():
        print(f"ERROR: Schema file not found: {schema_path}")
        return False

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Load export file
    export_path = Path(export_file)
    if not export_path.exists():
        print(f"ERROR: Export file not found: {export_file}")
        return False

    print(f"Loading export file: {export_file}")
    # Automatically detect and handle gzip compression
    if export_path.suffix == ".gz":
        with gzip.open(export_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
    else:
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    print(f"✓ Loaded {len(data)} objects")
    print("\nValidating against schema...")

    # Validate
    try:
        # Use Draft7Validator with format checking
        validator_cls = jsonschema.Draft7Validator
        validator = validator_cls(schema)

        errors = list(validator.iter_errors(data))

        if not errors:
            print("✓ Validation successful!")
            print(
                "  (Note: Schema validates core structure; export may contain additional fields)"
            )

            # Print statistics
            models = Counter(item.get("model", "unknown") for item in data)

            print("\nBreakdown by model:")
            for model, count in models.most_common():
                print(f"  {model}: {count}")

            return True
        else:
            print("✗ Validation failed!")
            print(f"\nFound {len(errors)} error(s):\n")

            for i, e in enumerate(errors[:10], 1):
                print(f"Error {i}:")
                print(f"  Message: {e.message}")
                # If the path is empty, show a clear root indicator
                path_str = " -> ".join(str(p) for p in e.path) if e.path else "root"
                print(f"  Path: {path_str}")
                if e.schema_path:
                    print(
                        f"  Schema path: {' -> '.join(str(p) for p in e.schema_path)}"
                    )
                print()

            if len(errors) > 10:
                print(f"... and {len(errors) - 10} more errors")

            return False

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print(USAGE)
        print("\nExamples:")
        print("  python validate_export.py data/rules_database.json")
        print("  python validate_export.py data/rules_en.json.gz")
        print("  python validate_export.py shared_rules.json")
        sys.exit(1)

    export_file = sys.argv[1]
    success = validate_export(export_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
