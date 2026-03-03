# Comprehensive Database Sharing & Rule Import/Export Guide

> 📚 **Documentation Overview:**
>
> - **Quick start?** → [QUICKSTART_SHARING.md](QUICKSTART_SHARING.md) (5-15 min read)
> - **This guide** → Advanced features, filtering, and team workflows (30+ min read)
> - **Setup info?** → [data/README.md](data/README.md) & [schemas/README.md](schemas/README.md)

## Overview

This guide explains how to share the Rule Editor database between installations while managing user data securely, and how to export/import individual rules with their relationships.

## Why JSON Fixtures?

We use Django's native JSON serialization instead of SQL dumps because:

1. **Database-agnostic**: Works with SQLite, PostgreSQL, MySQL - same file for all
2. **Security**: Can strip user data (passwords, sessions) programmatically
3. **Version control friendly**: Human-readable, can diff changes
4. **Selective export**: Easy to filter by language, dimension, date
5. **Cross-platform**: Works on Windows, macOS, Linux identically
6. **Django integration**: Uses built-in tools, handles relationships automatically

**vs SQL dumps:** SQL dumps are database-specific, include password hashes, and bypass Django's ORM validation.

## Export Format & Schema

The export format is a JSON array of Django fixture objects. Each object has:

- `model`: Django model identifier (e.g., `"rules.rule"`)
- `pk`: Primary key (integer)
- `fields`: Dictionary of field names and values

**JSON Schema:** A complete JSON Schema (Draft 7) is available in `schemas/rules_export_schema.json` for validation and documentation.

**Validation:**

```bash
# Install validator
pip install jsonschema

# Validate an export
python validate_export.py data/rules_database.json
```

See [schemas/README.md](schemas/README.md) for complete schema documentation.

## Quick Start: Language-Specific Imports

For faster setup and efficient storage, use language-specific exports with gzip compression:

```bash
# 1. Create your admin user
python manage.py createsuperuser

# 2. Import one or more languages (automatically decompressed)
# English only (927 KB compressed, 2,513 rules):
python manage.py import_rules_db --input=data/rules_en.json.gz --assign-to=yourusername

# German only (840 KB compressed, 2,718 rules):
python manage.py import_rules_db --input=data/rules_de.json.gz --assign-to=yourusername

# French only (1.1 MB compressed, 2,735 rules):
python manage.py import_rules_db --input=data/rules_fr.json.gz --assign-to=yourusername

# Or import all languages:
for lang in en de fr; do
  python manage.py import_rules_db --input=data/rules_${lang}.json.gz --assign-to=yourusername
done
```

**Advantages of language-specific compressed files:**

- Faster imports (only what you need)
- 95% smaller files with gzip compression (~1MB vs ~18MB originally)
- Excellent for version control and storage
- Automatic decompression on import
- Easier to update individual languages

---

## Data directory & pre-populated files

This repository ships gzip-compressed, language-scoped exports in `data/` for efficient storage:

- `data/rules_en.json.gz` — English (927 KB compressed, 2,513 rules, 28,230 objects)
- `data/rules_de.json.gz` — German (840 KB compressed, 2,718 rules, 24,411 objects)
- `data/rules_fr.json.gz` — French (1.1 MB compressed, 2,735 rules, 29,443 objects)

**Storage benefit**: ~95% space reduction (18-20MB → ~1MB each) with automatic decompression on import.

Tip: The `.gitignore` ignores `data/*` by default but explicitly allows these compressed files to keep the repo lean while providing useful starter data.

To regenerate these files from your current DB:

```bash
# Using Django management command (compression via .gz extension)
python manage.py export_rules_db --output=data/rules_en.json.gz --language=en
python manage.py export_rules_db --output=data/rules_de.json.gz --language=de
python manage.py export_rules_db --output=data/rules_fr.json.gz --language=fr

# Or using standalone script
python3 export_db_standalone.py database/db.sqlite3 data/rules_en.json.gz --language=en
python3 export_db_standalone.py database/db.sqlite3 data/rules_de.json.gz --language=de
python3 export_db_standalone.py database/db.sqlite3 data/rules_fr.json.gz --language=fr
```

---

## Filtering exports and update mode

Both the standalone exporter and the Django management command support rich filters and an update mode on import.

### Available export filters

- `--language=<lang>` — Filter by language (en, de, fr)
- `--created-after=<YYYY-MM-DD>` — Records created on/after date
- `--created-before=<YYYY-MM-DD>` — Records created on/before date
- `--updated-after=<YYYY-MM-DD>` — Records updated on/after date
- `--updated-before=<YYYY-MM-DD>` — Records updated on/before date
- `--rule-ids=<ids>` — Export specific rule IDs (comma-separated)
- `--dimension=<name>` — Filter by diversity dimension (Django command only)

Examples (standalone):

```bash
# By language (with compression)
python3 export_db_standalone.py database/db.sqlite3 data/recent_en.json.gz --language=en

# By dates
python3 export_db_standalone.py database/db.sqlite3 data/created_2024.json.gz --created-after=2024-01-01
python3 export_db_standalone.py database/db.sqlite3 data/updated_2024.json.gz --updated-after=2024-01-01

# Specific rule IDs (with all related data, compressed)
python3 export_db_standalone.py database/db.sqlite3 data/some_rules.json.gz --rule-ids=123,456,789

# Combine filters
python3 export_db_standalone.py database/db.sqlite3 data/specific_en.json.gz --rule-ids=100,200 --language=en
```

Examples (Django):

```bash
python manage.py export_rules_db --output=filtered.json.gz --language=de \
  --created-after=2024-01-01 --updated-before=2024-12-31 --rule-ids=101,202
```

### Import update mode

Use `--update` (alias: `--merge`) to update existing records instead of only inserting:

```bash
python manage.py import_rules_db --input=updates.json --update --assign-to=your_username

# Update only (skip creating new ones)
python manage.py import_rules_db --input=updates.json --update --skip-existing --assign-to=your_username
```

Notes:

- Update detection uses unique fields (e.g., lemma+language+trigger for rules)
- `--ignore-pk` can be used to avoid PK collisions when merging from different sources
- Dry run is available via `--dry-run`

---

## Command reference (concise)

### Export (standalone)

```bash
python3 export_db_standalone.py <db_path> <output_path> [options]

Options:
  --language=<lang>
  --created-after=<date> --created-before=<date>
  --updated-after=<date> --updated-before=<date>
  --rule-ids=<ids>
```

### Export (Django)

```bash
python manage.py export_rules_db [options]

Options:
  --output=<path>              # Output file (use .json.gz for compression)
  --compress                   # Compress with gzip (auto if .gz extension)
  --language=<lang>
  --created-after=<date> --created-before=<date>
  --updated-after=<date> --updated-before=<date>
  --since=<date>              # Alias for --updated-after
  --rule-ids=<ids>
  --dimension=<name>
```

### Import

```bash
python manage.py import_rules_db [options]

Options:
  --input=<path>  # required
  --update | --merge
  --skip-existing
  --assign-to=<username>
  --dry-run
  --ignore-pk
```

## Part 2: Usage

### Exporting Database (Without Users)

```bash
# Export all rule data, excluding users and sessions (with compression)
python manage.py export_rules_db --output=shared_rules.json.gz

# Or export only specific models, compressed
python manage.py export_rules_db --output=shared_rules.json.gz --exclude-linguistic-data

# Using --compress flag explicitly (can use .json extension)
python manage.py export_rules_db --output=shared_rules.json --compress
```

This creates a JSON file with:

- ✅ All rules, alternatives, diversity dimensions
- ✅ Training sentences, false positives
- ✅ Sources, categories, tags
- ✅ Linguistic data (nouns, verbs, adjectives)
- ❌ Users, passwords, sessions
- ❌ Admin logs, permissions

### Importing Database (With New Users)

```bash
# 1. Set up a fresh database
python manage.py migrate

# 2. Create your admin user
python manage.py createsuperuser

# 3. DRY RUN: Analyze what would be imported (auto-decompresses .gz)
python manage.py import_rules_db --input=shared_rules.json.gz --assign-to=yourusername --dry-run

# 4. Import the shared rules and assign ownership to your user
python manage.py import_rules_db --input=shared_rules.json.gz --assign-to=yourusername
```

**Important flags:**

- `--dry-run`: Show detailed analysis without making changes (shows duplicates, conflicts, samples)
- `--ignore-pk`: Generate new primary keys and detect duplicates by content (prevents PK conflicts when merging from different sources)
- `--skip-existing`: Skip objects that already exist
- `--merge`: Update existing objects with imported data
- `--assign-to=USERNAME`: Assign all imported data to a specific user

**Merging data from multiple sources:**

When importing rules from different installations that might have overlapping IDs:

```bash
# First, analyze for conflicts (works with .gz files automatically)
python manage.py import_rules_db --input=other_team_rules.json.gz --dry-run

# If PK conflicts detected, use --ignore-pk to generate new IDs
python manage.py import_rules_db --input=other_team_rules.json.gz --ignore-pk --skip-existing --assign-to=yourusername
```

The `--ignore-pk` flag will:

- Ignore imported primary keys
- Generate new sequential IDs
- Detect true duplicates by comparing content (lemma, trigger, language, etc.)
- Skip true duplicates automatically
- Remap foreign key relationships correctly

# Or import without assigning (all user references will be null)

python manage.py import_rules_db --input=shared_rules.json

# 4. (Optional) Assign ownership later if needed

python manage.py assign_rule_ownership --username=yourusername

````

**Important:** The `--assign-to` flag assigns ownership to your user for ALL imported objects that have user references (rules, alternatives, training sentences, sources, categories, etc.). This ensures proper attribution and prevents permission issues.

### Exporting Individual Rules

```bash
# Export a single rule by ID (compressed)
python manage.py export_rule --id=123 --output=my_rule.json.gz

# Export multiple rules
python manage.py export_rule --id=123,456,789 --output=my_rules.json.gz

# Export rules by search criteria (with compression)
python manage.py export_rule --lemma="chairman" --language=en --output=chairman_rules.json.gz

# Export with all related data (alternatives, training sentences, etc.)
python manage.py export_rule --id=123 --output=full_rule.json.gz --full
````

### Importing Individual Rules

```bash
# Import a rule (works with .json or .json.gz)
python manage.py import_rule --input=my_rule.json.gz

# Import without overwriting existing rules
python manage.py import_rule --input=my_rule.json.gz --skip-existing

# Import and assign to specific user
python manage.py import_rule --input=my_rule.json.gz --owner=yourusername
```

## Part 3: Advanced Usage

### Filtering Exports

**By Language:**

```bash
# Export only English rules (compressed)
python manage.py export_rules_db --output=rules_en.json.gz --language=en

# Export only German rules
python manage.py export_rules_db --output=rules_de.json.gz --language=de

# Export only French rules
python manage.py export_rules_db --output=rules_fr.json.gz --language=fr

# Standalone export (doesn't require Django, compression via .gz extension)
python3 export_db_standalone.py database/db.sqlite3 data/rules_en.json.gz --language=en
```

**By Date Range:**

```bash
# Export rules created after a date (compressed)
python manage.py export_rules_db --output=new_rules.json.gz --created-after=2024-01-01

# Export rules created within a date range
python manage.py export_rules_db --output=q1_rules.json.gz --created-after=2024-01-01 --created-before=2024-03-31

# Export rules updated after a date
python manage.py export_rules_db --output=recent_updates.json.gz --updated-after=2024-06-01

# Export rules updated before a date
python manage.py export_rules_db --output=old_rules.json.gz --updated-before=2023-12-31

# Combine filters
python manage.py export_rules_db --output=recent_en.json.gz --language=en --updated-after=2024-01-01

# Standalone export with filters
python3 export_db_standalone.py database/db.sqlite3 data/recent_en.json.gz --language=en --created-after=2024-01-01
```

**By Specific Rule IDs:**

```bash
# Export specific rules by ID with compression (includes all related data)
python manage.py export_rules_db --output=specific_rules.json.gz --rule-ids=123,456,789

# Standalone export with rule IDs (auto-compress via .gz extension)
python3 export_db_standalone.py database/db.sqlite3 data/my_rules.json.gz --rule-ids=100,200,300

# Combine with other filters (rules must match ALL filters)
python3 export_db_standalone.py database/db.sqlite3 data/specific_en.json.gz --rule-ids=100,200,300 --language=en
```

**What gets exported with specific rule IDs:**

- The specified rules
- All alternatives for those rules
- All training sentences for those rules
- All false positives for those rules
- All rule-diversity dimension links
- Related sources and linguistic data
- Categories and dimensions (to maintain relationships)

**By Diversity Dimension:**

```bash
# Export specific diversity dimension (compressed)
python manage.py export_rules_db --output=gender_rules.json.gz --dimension=gender_orientation

# Export with multiple filters
python manage.py export_rules_db --output=recent_gender_en.json.gz --dimension=gender --language=en --updated-after=2024-01-01
```

**File Size Optimization:**

When exporting large databases, compression significantly reduces file sizes:

```bash
# Split by language with compression (recommended for large databases)
# Results: ~95% smaller files (1MB vs ~18MB per language)
python3 export_db_standalone.py database/db.sqlite3 data/rules_en.json.gz --language=en
python3 export_db_standalone.py database/db.sqlite3 data/rules_de.json.gz --language=de
python3 export_db_standalone.py database/db.sqlite3 data/rules_fr.json.gz --language=fr

# Export only recent changes for incremental updates (compressed)
python3 export_db_standalone.py database/db.sqlite3 data/updates_2024.json.gz --created-after=2024-01-01
```

### Importing with Update Mode

**Update Existing Records:**

```bash
# Update existing records instead of creating new ones (auto-decompresses .gz)
python manage.py import_rules_db --input=updated_rules.json.gz --update

# Same as --merge (both flags work)
python manage.py import_rules_db --input=updated_rules.json.gz --merge

# Skip new records, only update existing ones
python manage.py import_rules_db --input=updated_rules.json.gz --update --skip-existing
```

The `--update` flag will:

- Update existing records that match (by unique fields like lemma+language+trigger)
- Insert new records that don't exist yet
- Preserve local changes if `--skip-existing` is also used

### Sharing Between Teams

**Team A (Exporter):**

```bash
# Export rules modified in the last 30 days (compressed)
python manage.py export_rules_db --output=recent_rules.json.gz --updated-after=2024-10-01

# Export specific diversity dimensions
python manage.py export_rules_db --output=gender_rules.json.gz --dimension=gender_orientation
```

**Team B (Importer):**

```bash
# Import new rules, skip duplicates (auto-decompresses .gz)
python manage.py import_rules_db --input=recent_rules.json.gz --skip-existing

# Import and merge/update with existing data
python manage.py import_rules_db --input=gender_rules.json.gz --update
```

### Syncing Production to Development

```bash
# On production server (compressed)
python manage.py export_rules_db --output=/tmp/prod_rules.json.gz

# Download and import to dev (auto-decompresses)
scp prod:/tmp/prod_rules.json.gz ./
python manage.py import_rules_db --input=prod_rules.json.gz --merge
```

### Version Control Workflow

```bash
# Export to versioned fixtures (compressed)
python manage.py export_rules_db --output=fixtures/rules_v2.1.json.gz

# Commit to git
git add fixtures/rules_v2.1.json.gz
git commit -m "Update rules fixture v2.1"

# On another machine
git pull
python manage.py import_rules_db --input=fixtures/rules_v2.1.json.gz --merge
```

## Part 4: Data Relationships Preserved

When exporting rules, the following relationships are automatically included:

### Rule Export Includes:

- ✅ **Alternatives** (with their tags and sources)
- ✅ **Training Sentences** (with sources)
- ✅ **False Positives**
- ✅ **Diversity Dimensions** (associations)
- ✅ **Sources** (referenced in rules/alternatives)
- ✅ **Categories** (parent of diversity dimensions)
- ✅ **Tags** (taggit tags)
- ✅ **Rule Links** (self-referential many-to-many)
- ✅ **Parent/Child Rules** (hierarchical relationships)
- ✅ **Sanctions** (source references)

### Excluded for Privacy:

- ❌ User accounts
- ❌ Passwords & sessions
- ❌ Admin logs
- ❌ User-specific evaluations (optional)

## Part 5: File Format

The export format is Django's natural JSON fixture format:

```json
[
  {
    "model": "rules.rule",
    "pk": 123,
    "fields": {
      "lemma": "chairman",
      "language": "en",
      "word_types": "n",
      "createdby": null,
      "ownedby": null,
      "created_at": "2024-01-01",
      ...
    }
  },
  {
    "model": "rules.alternative",
    "pk": 456,
    "fields": {
      "rule": 123,
      "lemma": "chairperson",
      ...
    }
  }
]
```

## Part 6: Best Practices

### For Sharing:

1. **Always exclude users** when sharing publicly
2. **Version your exports** (include date or version in filename)
3. **Document changes** in commit messages
4. **Test imports** on a fresh database first
5. **Use `--skip-existing`** to avoid overwriting local changes

### For Production:

1. **Backup before importing** large datasets
2. **Use `--merge`** for production imports
3. **Review diffs** before importing from external sources
4. **Assign ownership** after import for accountability
5. **Run `check_rules`** after import to validate data

### For Development:

1. **Keep fixtures in version control** for team sync
2. **Use separate fixtures** for different features/domains
3. **Export frequently** to track changes
4. **Import selectively** to test specific features

## Part 7: Troubleshooting

### Import Fails with Integrity Error

```bash
# Try importing dependencies first
python manage.py import_rules_db --input=data.json --models=categories,diversitydimensions,sources
python manage.py import_rules_db --input=data.json --models=rules,alternatives
```

### Duplicate Rules After Import

```bash
# Use skip-existing flag
python manage.py import_rules_db --input=data.json --skip-existing

# Or remove duplicates
python manage.py cleanup_duplicate_rules
```

### Missing Related Objects

```bash
# Import with dependencies
python manage.py import_rule --input=rule.json --with-dependencies
```

## Security Considerations

1. **Never share the raw SQLite database** - it contains password hashes
2. **Always use JSON exports** for sharing
3. **Review exported data** before sharing externally
4. **Consider data sensitivity** in comments and notes fields
5. **Strip personal information** from training sentences if needed

### User Reference Handling

**Export Behavior:**
All user references (`createdby`, `ownedby`) are automatically set to `null` during export for security. This applies to:

- Rules
- Alternatives
- Training Sentences
- False Positives
- Sources
- Categories
- Diversity Dimensions
- Lemmatizations
- All linguistic data (nouns, verbs, adjectives)
- Rule evaluations

**Import Behavior:**
When importing, you have three options for user assignment:

1. **Assign during import** (Recommended):

   ```bash
   python manage.py import_rules_db --input=data.json --assign-to=username
   python manage.py import_rule --input=rule.json --owner=username
   ```

   All imported objects will be assigned to the specified user.

2. **Assign after import**:

   ```bash
   python manage.py import_rules_db --input=data.json
   python manage.py assign_rule_ownership --username=username
   ```

   Import with null user references, then assign ownership separately.

3. **Leave unassigned**:
   ```bash
   python manage.py import_rules_db --input=data.json
   ```
   All user references remain `null`. This is acceptable for viewing data but may cause issues if code expects user attribution.

**Why This Matters:**

- Prevents security issues (no password exposure)
- Allows each installation to have its own users
- Enables proper attribution within each team
- Avoids FK constraint errors when users don't exist
- Makes sharing between organizations possible

## Performance & File Sizes

- **Full database export** (10,000 rules): ~30 seconds, 5-20 MB
- **Individual rule export**: <1 second, 1-10 KB
- **Import speed**: ~2 minutes for 10,000 rules
- **Compression**: Use gzip for 80-90% size reduction

## Command Reference

### Export Commands

```bash
# Full database (no users)
python manage.py export_rules_db --output=FILE

# Filtered exports
python manage.py export_rules_db --language=en --output=FILE
python manage.py export_rules_db --dimension=gender --output=FILE
python manage.py export_rules_db --since="2024-11-01" --output=FILE
python manage.py export_rules_db --exclude-linguistic-data --output=FILE

# Individual rules
python manage.py export_rule --id=123 --output=FILE
python manage.py export_rule --id=123,456,789 --output=FILE
python manage.py export_rule --lemma="chairman" --language=en --output=FILE
```

### Import Commands

```bash
# Full import with user assignment (RECOMMENDED)
python manage.py import_rules_db --input=FILE --assign-to=username

# Dry run to see what would be imported
python manage.py import_rules_db --input=FILE --dry-run

# Import with conflict handling
python manage.py import_rules_db --input=FILE --skip-existing
python manage.py import_rules_db --input=FILE --merge
python manage.py import_rules_db --input=FILE --dry-run

# Import from different source (prevent PK conflicts)
python manage.py import_rules_db --input=FILE --ignore-pk --skip-existing --assign-to=username

# Individual rules
python manage.py import_rule --input=FILE --owner=username
python manage.py import_rule --input=FILE --skip-existing
```

### Utility Commands

```bash
# Assign ownership after import
python manage.py assign_rule_ownership --username=USER [--language=LANG]

# Clean duplicates
python manage.py cleanup_duplicate_rules --dry-run
python manage.py cleanup_duplicate_rules --remove --keep=newest

# List models with user references
python manage.py list_user_reference_models

# Export database without Django installed (standalone)
python3 export_db_standalone.py data/rules_database.json
```

**Note:** The `export_db_standalone.py` script is useful when you need to export the database but don't have Django or dependencies installed. It directly reads the SQLite file and creates a compatible JSON export.

## Troubleshooting

**Dry run shows PK conflicts:**

Use `--dry-run` first to analyze:

```bash
python manage.py import_rules_db --input=data.json --dry-run
```

If conflicts detected:

```bash
python manage.py import_rules_db --input=data.json --ignore-pk --skip-existing
```

**Import fails with integrity error:**

```bash
python manage.py import_rules_db --input=data.json --skip-existing
```

**Duplicates after import:**

```bash
python manage.py cleanup_duplicate_rules --remove
```

**User not found:**
Create the user first: `python manage.py createsuperuser`

**Import seems stuck:**
Large imports take time. Check file size growth: `watch -n 5 'ls -lh database/db.sqlite3'`

**Merging rules from multiple teams:**

```bash
# Analyze first
python manage.py import_rules_db --input=team_a_rules.json --dry-run
python manage.py import_rules_db --input=team_b_rules.json --dry-run

# Import with conflict handling
python manage.py import_rules_db --input=team_a_rules.json --ignore-pk --skip-existing --assign-to=user1
python manage.py import_rules_db --input=team_b_rules.json --ignore-pk --skip-existing --assign-to=user2
```

## Testing

```bash
# Test user reference handling
python test_user_references.py

# Full test suite
python test_sharing.py

# Dry run any command
python manage.py COMMAND --dry-run

# Validate export format
python validate_export.py data/rules_database.json
```

## JSON Schema

A complete JSON Schema (Draft 7) is provided for the export format:

- **Location:** `schemas/rules_export_schema.json`
- **Documentation:** `schemas/README.md`
- **Purpose:** Validates export structure, documents field types, enables IDE autocomplete

**Benefits:**

- Validate exports before sharing
- Document expected field types and values
- Enable IDE validation and autocomplete
- Ensure compatibility between versions

**Models Defined:**

- Core: Category, DiversityDimension, Source, Rule, Alternative, TrainingSentence, FalsePositive
- Linguistic: EnglishNoun/Verb/Adjective, GermanNoun/Verb/Adjective, FrenchNoun
- Relationships: RuleDiversityDimension, Lemmatization, RuleStructureEvaluation

See `schemas/README.md` for complete documentation.
