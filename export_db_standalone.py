#!/usr/bin/env python3
"""
Standalone database export script that doesn't require Django to be installed.
This script reads the SQLite database and exports it in a format compatible with
the import_rules_db management command.
"""

import sqlite3
import sys
import os


def _index_map(columns):
    """Return a mapping of column name -> index for quick lookups."""
    return {name: i for i, name in enumerate(columns)}


def _build_filtered_rule_ids(
    cursor,
    language_filter=None,
    created_after=None,
    created_before=None,
    updated_after=None,
    updated_before=None,
    rule_ids=None,
):
    """Build the set of rule IDs matching provided filters and print a short summary."""
    where_clauses = []
    params = []

    if rule_ids:
        placeholders = ",".join("?" * len(rule_ids))
        where_clauses.append(f"id IN ({placeholders})")
        params.extend(rule_ids)

    if language_filter:
        where_clauses.append("language = ?")
        params.append(language_filter)

    if created_after:
        where_clauses.append("created_at >= ?")
        params.append(created_after)

    if created_before:
        where_clauses.append("created_at <= ?")
        params.append(created_before)

    if updated_after:
        where_clauses.append("updated_at >= ?")
        params.append(updated_after)

    if updated_before:
        where_clauses.append("updated_at <= ?")
        params.append(updated_before)

    filtered_rule_ids = set()
    if where_clauses:
        where_sql = " AND ".join(where_clauses)
        sql = f"SELECT id FROM rules_rule WHERE {where_sql} ORDER BY id"
        cursor.execute(sql, params)
        filtered_rule_ids = {row[0] for row in cursor.fetchall()}
        print(f"Applied filters: found {len(filtered_rule_ids)} matching rules")
        if rule_ids:
            print(f"  - Specific rule IDs: {rule_ids}")
        if language_filter:
            print(f"  - Language: {language_filter}")
        if created_after:
            print(f"  - Created after: {created_after}")
        if created_before:
            print(f"  - Created before: {created_before}")
        if updated_after:
            print(f"  - Updated after: {updated_after}")
        if updated_before:
            print(f"  - Updated before: {updated_before}")

    return filtered_rule_ids


def _language_specific_table_allowed(table_name, language_filter):
    """Return True if the table should be considered for the given language filter."""
    if not language_filter:
        return True
    if language_filter == "en":
        # Skip german/french linguistic tables
        return not (
            table_name.startswith("rules_german")
            or table_name.startswith("rules_french")
        )
    if language_filter == "de":
        return not (
            table_name.startswith("rules_english")
            or table_name.startswith("rules_french")
        )
    if language_filter == "fr":
        return not (
            table_name.startswith("rules_english")
            or table_name.startswith("rules_german")
        )
    return True


def _should_include_row(table_name, row, idx, filtered_rule_ids, language_filter):
    """Centralize per-row inclusion logic for filters and relationships."""
    if not filtered_rule_ids:
        # No rule-based filtering requested; only language-specific checks apply
        if language_filter and table_name in {"rules_source", "rules_lemmatization"}:
            lang_col = idx.get("language")
            return lang_col is None or row[lang_col] == language_filter
        return _language_specific_table_allowed(table_name, language_filter)

    # If we do have a filtered set of rules, ensure related tables match
    if table_name == "rules_rule":
        return row[idx.get("id", 0)] in filtered_rule_ids

    if table_name in {
        "rules_alternative",
        "rules_trainingsentence",
        "rules_falsepositive",
        "rules_rulestructureevaluation",
    }:
        rule_id_col = idx.get("rule_id")
        return rule_id_col is None or row[rule_id_col] in filtered_rule_ids

    if language_filter and table_name in {"rules_source", "rules_lemmatization"}:
        lang_col = idx.get("language")
        return lang_col is None or row[lang_col] == language_filter

    # Language-specific tables (english/german/french) when language filter set
    return _language_specific_table_allowed(table_name, language_filter)


# DB columns that are foreign keys. Their fixture field name has no "_id"
# suffix (Django fixture format); regular columns that merely end in "_id"
# (text_id) keep their name. Emitting raw column names produced files the
# Django deserializer rejects outright.
FK_COLUMNS = {
    "rule_id",
    "parent_id",
    "rule_translation_source_id",
    "diversity_dimension_id",
    "category_id",
    "source_id",
    "createdby_id",
    "ownedby_id",
}

# Junction/m2m columns never appear here because their tables are not in
# DB_TABLE_TO_MODEL; tags, links and sanctions deliberately do not travel.


def _row_to_fixture(model_name, row, columns, user_fields, bool_columns=frozenset()):
    """Convert a DB row to a Django fixture dict, handling user refs and types."""
    fields = {}
    idx = _index_map(columns)
    for i, col_name in enumerate(columns):
        if col_name == "id":
            continue
        value = None if col_name in user_fields else row[i]
        field_name = (
            col_name[: -len("_id")] if col_name in FK_COLUMNS else col_name
        )
        if value is not None and col_name in bool_columns:
            value = bool(value)
        fields[field_name] = (
            None
            if value is None
            else value if isinstance(value, (int, float, bool)) else str(value)
        )
    return {
        "model": model_name,
        "pk": row[
            idx.get("id", 0)
        ],  # id as PK (assumed first column if missing PRAGMA)
        "fields": fields,
    }


def get_table_data(cursor, table_name):
    """Get all data from a table in deterministic order (by primary key).

    Returns (rows, columns, bool_columns): SQLite stores booleans as 0/1,
    but Django fixtures (and the export schema) carry true/false, so callers
    need to know which columns are declared bool.
    """
    try:
        # Order by id (primary key) for deterministic output
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY id")
        rows = cursor.fetchall()

        # Get column names and declared types
        cursor.execute(f"PRAGMA table_info({table_name})")
        table_info = cursor.fetchall()
        columns = [col[1] for col in table_info]
        bool_columns = {col[1] for col in table_info if col[2].lower() == "bool"}

        return rows, columns, bool_columns
    except sqlite3.Error as e:
        print(f"Error reading table {table_name}: {e}", file=sys.stderr)
        return [], [], set()


def export_to_json(
    db_path,
    output_path,
    language_filter=None,
    created_after=None,
    created_before=None,
    updated_after=None,
    updated_before=None,
    rule_ids=None,
    compress=None,
):
    """Export the database to a JSON file in Django fixtures format

    Args:
        db_path: Path to SQLite database
        output_path: Path to output JSON file
        language_filter: Filter by language (en, de, fr)
        created_after: Filter records created after this date (YYYY-MM-DD)
        created_before: Filter records created before this date (YYYY-MM-DD)
        updated_after: Filter records updated after this date (YYYY-MM-DD)
        updated_before: Filter records updated before this date (YYYY-MM-DD)
        rule_ids: List of specific rule IDs to export (with their relations)
        compress: Force compression (True/False), or auto-detect from extension (None)
    """
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get list of tables
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    # Django app models (based on the management command)
    # Define in dependency order to ensure proper import sequence
    # Import shared model name constants
    from rules.model_constants import DB_TABLE_TO_MODEL

    model_tables = DB_TABLE_TO_MODEL

    # Process tables in dependency order (rules before their children, base
    # models first) so importers that validate references as they go never
    # see a child before its parent. Alphabetical order put alternatives
    # before rules.
    from rules.model_constants import IMPORT_ORDER, MODEL_TO_DB_TABLE

    sorted_model_tables = [
        (MODEL_TO_DB_TABLE[model], model)
        for model in IMPORT_ORDER
        if MODEL_TO_DB_TABLE.get(model) in model_tables
    ]

    # Fields that should be nullified (user references)
    # Use shared DB field names for user references
    from rules.model_constants import USER_FIELDS_DB

    user_fields = USER_FIELDS_DB

    fixtures = []
    total_records = 0

    # Compute filtered rule IDs once (if any filters provided)
    filtered_rule_ids = _build_filtered_rule_ids(
        cursor,
        language_filter=language_filter,
        created_after=created_after,
        created_before=created_before,
        updated_after=updated_after,
        updated_before=updated_before,
        rule_ids=rule_ids,
    )

    for table_name, model_name in sorted_model_tables:
        if table_name not in tables:
            continue

        rows, columns, bool_columns = get_table_data(cursor, table_name)

        if not rows:
            continue

        idx = _index_map(columns)
        for row in rows:
            if not _should_include_row(
                table_name, row, idx, filtered_rule_ids, language_filter
            ):
                continue
            fixtures.append(
                _row_to_fixture(model_name, row, columns, user_fields, bool_columns)
            )
            total_records += 1

    conn.close()

    # Write to output file via shared utility
    from rules.export_utils import dump_json, format_file_size

    output_path = dump_json(fixtures, output_path, indent=2, compress=compress)

    file_size = output_path.stat().st_size
    print(f"✓ Exported {total_records} records to {output_path}")
    print(f"✓ File size: {format_file_size(file_size)}")
    if output_path.suffix.lower() == ".gz":
        print("✓ Format: gzip compressed")
    print("\nTo import on another system:")
    print(
        f"  python manage.py import_rules_db --input={output_path.name} --assign-to=YOUR_USERNAME"
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python export_db_standalone.py <db_path> <output_path> [options]")
        print("\nOptions:")
        print("  --language=<lang>           Filter by language (en, de, fr)")
        print(
            "  --created-after=<date>      Filter records created after date (YYYY-MM-DD)"
        )
        print(
            "  --created-before=<date>     Filter records created before date (YYYY-MM-DD)"
        )
        print(
            "  --updated-after=<date>      Filter records updated after date (YYYY-MM-DD)"
        )
        print(
            "  --updated-before=<date>     Filter records updated before date (YYYY-MM-DD)"
        )
        print(
            "  --rule-ids=<ids>            Export specific rule IDs (comma-separated)"
        )
        print("\nExamples:")
        print(
            "  python export_db_standalone.py database/db.sqlite3 data/rules_database.json"
        )
        print(
            "  python export_db_standalone.py database/db.sqlite3 data/rules_en.json --language=en"
        )
        print(
            "  python export_db_standalone.py database/db.sqlite3 data/output.json.gz --language=en"
        )
        print(
            "  python export_db_standalone.py database/db.sqlite3 data/created_2024.json --created-after=2024-01-01"
        )
        print(
            "  python export_db_standalone.py database/db.sqlite3 data/specific_rules.json --rule-ids=123,456,789"
        )
        print(
            "  python export_db_standalone.py database/db.sqlite3 data/output.json --compress"
        )
        sys.exit(1)

    db_path = sys.argv[1]
    output_path = sys.argv[2]
    language_filter = None
    created_after = None
    created_before = None
    updated_after = None
    updated_before = None
    rule_ids = None
    compress = None

    # Parse optional filters
    for arg in sys.argv[3:]:
        if arg.startswith("--language="):
            language_filter = arg.split("=", 1)[1]
        elif arg.startswith("--created-after="):
            created_after = arg.split("=", 1)[1]
        elif arg.startswith("--created-before="):
            created_before = arg.split("=", 1)[1]
        elif arg.startswith("--updated-after="):
            updated_after = arg.split("=", 1)[1]
        elif arg.startswith("--updated-before="):
            updated_before = arg.split("=", 1)[1]
        elif arg.startswith("--rule-ids="):
            ids_str = arg.split("=", 1)[1]
            rule_ids = [
                int(id.strip()) for id in ids_str.split(",") if id.strip().isdigit()
            ]
        elif arg == "--compress":
            compress = True

    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    export_to_json(
        db_path,
        output_path,
        language_filter,
        created_after,
        created_before,
        updated_after,
        updated_before,
        rule_ids,
        compress,
    )
