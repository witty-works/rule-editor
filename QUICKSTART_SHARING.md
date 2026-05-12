# Quick Start: Sharing & Importing Rules

This guide gets you started with sharing and importing rule data.

> **Need more details?** See the [Comprehensive Sharing Guide](SHARING_GUIDE.md) for advanced filtering, team workflows, and technical details. **First time setting up?** Start with [Scenario 1](#scenario-1-first-time-setup-receiving-shared-data) below.

## Scenario 1: First Time Setup (Receiving Shared Data)

You're joining the team and want to import the shared rules database.

**Pre-populated databases available:** The repository includes language-specific exports in `data/` (gzip-compressed for efficient storage):

- **English**: `rules_en.json.gz` (927 KB compressed, 2,513 rules)
- **German**: `rules_de.json.gz` (840 KB compressed, 2,718 rules)
- **French**: `rules_fr.json.gz` (1.1 MB compressed, 2,735 rules)

```bash
# 1. Set up your environment
git clone https://github.com/witty-works/rule-editor.git
cd rule-editor
pipenv install
pipenv shell

# 2. Create database
mkdir database
python manage.py migrate

# 3. Create your admin user
python manage.py createsuperuser
# Enter: username, email, password

# 4. DRY RUN: See what would be imported (example with English)
python manage.py import_rules_db --input=data/rules_en.json.gz --assign-to=your_username --dry-run

# 5. Import the language(s) you need
# Import just English:
python manage.py import_rules_db --input=data/rules_en.json.gz --assign-to=your_username

# Or import all languages:
for lang in en de fr; do
  python manage.py import_rules_db --input=data/rules_${lang}.json.gz --assign-to=your_username
done

# Note: Using --assign-to automatically assigns ALL imported data to your user
# This includes rules, alternatives, training sentences, sources, etc.

# 6. Verify import
python manage.py check_rules

# 7. Start server
python manage.py runserver 8100

# 8. Visit http://127.0.0.1:8100/
```

**That's it!** You now have the rules database with your own admin account.

---

## Scenario 2: Sharing Your Database (Without Users)

You want to share your rules with another team/person.

```bash
# Export everything (no users included)
python manage.py export_rules_db --output=shared_rules.json

# Share the file
# - Email: shared_rules.json
# - Git: commit to repo
# - Cloud: upload to shared drive
```

The exported file:

- ✅ Contains all rules, alternatives, categories, etc.
- ❌ Does NOT contain any user accounts or passwords
- 📦 Can be imported by anyone following Scenario 1

---

## Scenario 3: Contributing a New Rule

You created a great new rule and want to share it.

```bash
# Find your rule ID in the admin interface (e.g., ID: 1234)

# Export just that rule with all its related data
python manage.py export_rule --id=1234 --output=my_new_rule.json

# Or export with compression for smaller file size
python manage.py export_rule --id=1234 --output=my_new_rule.json.gz

# Or use the new --rule-ids filter (works for multiple rules)
python3 export_db_standalone.py database/db.sqlite3 my_rules.json.gz --rule-ids=1234,5678

# Share my_new_rule.json.gz with your team
```

**What gets exported:**

- The specified rule(s)
- All alternatives
- All training sentences
- All false positives
- Diversity dimension links
- Related categories and sources

Your teammate imports it:

```bash
# Import the rule with ownership assignment (works with .json or .json.gz)
python manage.py import_rule --input=my_new_rule.json.gz --owner=their_username

# Or with the full DB import command
python manage.py import_rules_db --input=my_rules.json.gz --assign-to=their_username

# Check it in admin
python manage.py runserver 8100
```

---

## Scenario 4: Updating Existing Rules

You've made changes to existing rules and want to share updates.

```bash
# Export rules modified recently (date-based)
python manage.py export_rules_db --output=updates.json.gz --updated-after=2024-11-01

# Or using standalone script
python3 export_db_standalone.py database/db.sqlite3 data/updates.json.gz --updated-after=2024-11-01

# Share updates.json.gz
```

Your teammate merges the updates:

```bash
# Import and update existing records (automatically decompresses .gz)
python manage.py import_rules_db --input=updates.json.gz --update --assign-to=your_username

# Or skip existing (only add new rules)
python manage.py import_rules_db --input=updates.json.gz --skip-existing --assign-to=your_username
```

**Note:** `--update` (alias: `--merge`) updates existing records with new data from the import. Without any flag, existing records matched by PK are **overwritten** silently — always use `--dry-run` first when unsure.

---

## Scenario 5: Working with Specific Languages/Dimensions/Dates

Export only what you need using filters:

```bash
# Export only English rules
python manage.py export_rules_db --output=english_rules.json --language=en
python3 export_db_standalone.py database/db.sqlite3 data/rules_en.json.gz --language=en

# Export only German rules
python manage.py export_rules_db --output=german_rules.json --language=de
python3 export_db_standalone.py database/db.sqlite3 data/rules_de.json --language=de

# Export rules created after a date
python3 export_db_standalone.py database/db.sqlite3 data/new_rules.json --created-after=2024-01-01

# Export rules updated within a date range
python3 export_db_standalone.py database/db.sqlite3 data/q1_updates.json --updated-after=2024-01-01 --updated-before=2024-03-31

# Combine filters
python3 export_db_standalone.py database/db.sqlite3 data/recent_en.json --language=en --created-after=2024-06-01

# Export only gender-related rules
python manage.py export_rules_db --output=gender_rules.json --dimension=gender

# Export specific rule by lemma
python manage.py export_rule --lemma="chairman" --language=en --output=chairman.json
```

**Available filters:**

- `--language=<lang>` - en, de, or fr
- `--created-after=<date>` - YYYY-MM-DD format
- `--created-before=<date>` - YYYY-MM-DD format
- `--updated-after=<date>` - YYYY-MM-DD format
- `--updated-before=<date>` - YYYY-MM-DD format
- `--dimension=<name>` - diversity dimension filter (Django command only)

---

## Common Tasks

---

## Scenario 6: Merging Rules from Different Teams

You have rules from two different installations and want to merge them without conflicts.

```bash
# 1. Analyze what's in each export
python manage.py import_rules_db --input=team_a_rules.json --dry-run
python manage.py import_rules_db --input=team_b_rules.json --dry-run

# The dry run will show:
# - Total objects
# - PK conflicts (if any)
# - True duplicates
# - Sample records

# 2. Import first team's rules
python manage.py import_rules_db --input=team_a_rules.json --assign-to=team_a_user

# 3. Import second team's rules with conflict handling
python manage.py import_rules_db --input=team_b_rules.json --ignore-pk --skip-existing --assign-to=team_b_user

# --ignore-pk: Generates new PKs to avoid conflicts
# --skip-existing: Skips true duplicates (same lemma/trigger/language)
# --assign-to: Tracks which team contributed each rule

# 4. Clean up any remaining duplicates
python manage.py cleanup_duplicate_rules --dry-run
python manage.py cleanup_duplicate_rules --remove --keep=newest
```

**What `--ignore-pk` does:**

- Ignores imported primary keys and generates new sequential IDs
- Detects duplicates by content (not by ID)
- Remaps **all** foreign key relationships to the new IDs — this covers `rule`, `source`, `category`, `diversity_dimension`, self-referential `parent` / `rule_translation_source`, and user fields
- Prevents "PK already exists" errors when merging exports from different installations

---

## Quick Commands Reference

### Check what would be imported (dry run)

```bash
python manage.py import_rules_db --input=data.json --dry-run
```

### View duplicates without removing

```bash
python manage.py cleanup_duplicate_rules --dry-run
```

### Remove duplicates

```bash
python manage.py cleanup_duplicate_rules --remove
```

### Assign all unowned rules to yourself

```bash
python manage.py assign_rule_ownership --username=your_username --unowned-only
```

### Test rules after import

```bash
python manage.py check_rules
```

---

## File Size Estimates

- **Full database**: ~5-20 MB (depending on rule count)
- **Single rule**: ~1-10 KB (with all relations)
- **Language subset**: ~2-8 MB

Use a `.json.gz` output path to enable automatic gzip compression (typically 80–90% smaller):

```bash
# Export compressed — no extra flag needed, extension is enough
python manage.py export_rules_db --output=shared_rules.json.gz

# Import decompresses automatically
python manage.py import_rules_db --input=shared_rules.json.gz --assign-to=YOUR_USERNAME
```

---

## Troubleshooting

### "User not found" when importing

- You need to create a user first: `python manage.py createsuperuser`
- Or import without assigning: don't use `--assign-to` flag

### "Integrity error" during import

- Try: `python manage.py import_rules_db --input=data.json --skip-existing`
- Or clean duplicates first: `python manage.py cleanup_duplicate_rules --remove`

### Import seems stuck

- Large imports can take time (10,000+ rules = few minutes)
- Check database/db.sqlite3 file size - it should be growing

### Rules imported but not visible

- Clear browser cache
- Restart server
- Check filters in admin interface

---

## Best Practices

1. **Before importing**: Back up your database

   ```bash
   cp database/db.sqlite3 database/db.sqlite3.backup
   ```

2. **After importing**: Validate rules

   ```bash
   python manage.py check_rules
   ```

3. **When sharing**: Use descriptive filenames

   ```bash
   rules_2024-11-12_v2.1.json
   gender_rules_update_nov2024.json
   ```

4. **Version control**: Commit exports to git
   ```bash
   git add fixtures/rules_v2.1.json
   git commit -m "Update rules fixture v2.1 - added 50 new gender rules"
   ```

---

## Important: User Ownership

### What Happens to User References?

**During Export:**

- All user references (`createdby`, `ownedby`) are automatically set to `null`
- This applies to rules, alternatives, training sentences, sources, categories, and all other objects
- This is for security - no passwords or user accounts are included

**During Import:**

- **Option 1 - Assign during import (RECOMMENDED):**

  ```bash
  python manage.py import_rules_db --input=data.json --assign-to=username
  ```

  All imported objects are automatically assigned to your user.

- **Option 2 - Assign after import:**

  ```bash
  python manage.py import_rules_db --input=data.json
  python manage.py assign_rule_ownership --username=username
  ```

  Import first with null references, then assign ownership.

- **Option 3 - Leave unassigned:**
  ```bash
  python manage.py import_rules_db --input=data.json
  ```
  All objects have `null` user references. This works for viewing but may cause issues with some features.

### Why Does This Matter?

1. **Security**: Ensures no user credentials are shared
2. **Attribution**: Each team has proper ownership tracking
3. **Permissions**: Some features may check ownership
4. **Audit Trail**: Keeps track of who owns what in each installation

### Which Models Have User References?

User references (`createdby` and/or `ownedby`) exist on:

- Rules (has both `createdby` and `ownedby`)
- Alternatives
- Training Sentences
- False Positives
- Sources
- Categories
- Diversity Dimensions
- Lemmatizations
- All linguistic data (English/German/French nouns, verbs, adjectives)
- Rule Evaluations

All of these are handled automatically when you use `--assign-to` or `--owner` flags.

---

## Getting Help

- Full documentation: [SHARING_GUIDE.md](SHARING_GUIDE.md)
- Check command help: `python manage.py export_rules_db --help`
- Report issues: Open a GitHub issue
