# Data Directory

This directory contains pre-populated rule databases and source data files.

## Pre-populated Rule Databases

Language-specific database exports ready for immediate import (gzip-compressed for efficient storage):

| File               | Language | Rules | Compressed Size |
| ------------------ | -------- | ----- | --------------- |
| `rules_en.json.gz` | English  | ~2.5k | 927 KB          |
| `rules_de.json.gz` | German   | ~2.7k | 840 KB          |
| `rules_fr.json.gz` | French   | ~2.7k | 1.1 MB          |

**Storage Benefits**: Compressed files save ~95% space compared to uncompressed JSON (18MB → 927KB for English)

### Quick Import

The import tool automatically detects and decompresses `.gz` files:

```bash
# Import one language (automatically decompresses)
python manage.py import_rules_db --input=data/rules_en.json.gz --assign-to=YOUR_USERNAME

# Import all languages
for lang in en de fr; do
  python manage.py import_rules_db --input=data/rules_${lang}.json.gz --assign-to=YOUR_USERNAME
done
```

### File Contents

Each export includes:

- Rules with their triggers and lemmas
- All alternatives for each rule
- Training sentences and false positives
- Diversity dimension associations
- Related sources and categories
- Linguistic data (nouns, verbs, adjectives)

### Regenerating Exports

To regenerate these files with current database data:

```bash
# From project root (compress automatically via .gz extension)
python3 export_db_standalone.py database/db.sqlite3 data/rules_en.json.gz --language=en
python3 export_db_standalone.py database/db.sqlite3 data/rules_de.json.gz --language=de
python3 export_db_standalone.py database/db.sqlite3 data/rules_fr.json.gz --language=fr

# Or using Django management command with --compress flag
python manage.py export_rules_db --output=data/rules_en.json.gz --language=en
python manage.py export_rules_db --output=data/rules_de.json.gz --language=de
python manage.py export_rules_db --output=data/rules_fr.json.gz --language=fr
```

## Source Data Files

- `categories.json` - Rule categories
- `diversity_dimension_drivers.json` - Diversity dimension metadata
- `proficiency_levels.json` - Witty proficiency level definitions
- `german_adjectives.txt` - German adjective wordlist
- `german_nouns.txt` - German noun wordlist
- `verbs.csv` - Verb conjugation data
- Various CSV files - Legacy import data

## Git Configuration

The `.gitignore` is configured to:

- Ignore `data/*` by default (prevents accidentally committing large files)
- Explicitly allow `rules_*.json.gz` (compressed exports for efficient storage)
- This keeps the repository size manageable while providing starter data

**Compression Support**: All JSON files can be automatically compressed/decompressed during import/export operations. File extension-based detection (`.json.gz`) triggers automatic compression.

## File Size Guidelines

GitHub recommendations:

- ⚠️ Warning at 50MB
- ❌ Hard limit at 100MB

**Compressed storage**: Our language-specific files are now ~1MB each (originally ~18-20MB each)

- English: 927 KB (was 18 MB)
- German: 840 KB (was 17 MB)
- French: 1.1 MB (was 20 MB)

This provides ~95% storage reduction while maintaining full functionality.

## Documentation

Learn more about import/export features:

| Guide                                             | Purpose                                   |
| ------------------------------------------------- | ----------------------------------------- |
| [QUICKSTART_SHARING.md](../QUICKSTART_SHARING.md) | Common scenarios (5-15 min)               |
| [SHARING_GUIDE.md](../SHARING_GUIDE.md)           | Advanced features and workflows (30+ min) |
| [Main README](../README.md#documentation)         | Full project documentation                |
| [schemas/README.md](../schemas/README.md)         | JSON Schema validation                    |

**Quick Links:**

- Already have a compressed file? → [Import instructions](../QUICKSTART_SHARING.md#scenario-1-first-time-setup-receiving-shared-data)
- Generate compressed exports? → [Export commands](../SHARING_GUIDE.md#part-2-usage)
