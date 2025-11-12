# Rules Export JSON Schema

This directory contains the JSON Schema for the Witty Rules database export format.

## Schema File

- **`rules_export_schema.json`** - JSON Schema (Draft 7) defining the structure of rule exports

## Important Note

The current schema defines the **core required fields** for each model. The actual database export may contain additional fields that are:

- Computed/cached fields (e.g., `has_training_sentences`, `lemma_length`)
- Internal fields (e.g., `first_word_type`, `pattern`)
- Legacy fields from schema evolution

**The schema validates the minimum required structure for successful import/export.**

To see the complete list of fields in an actual export:

```bash
python3 -c "import json; data = json.load(open('data/rules_database.json')); print(json.dumps(data[0], indent=2))"
```

## What It Defines

The schema defines the complete structure of a rules database export, including:

### Core Models

- **rules.category** - Rule categories (organizational-diversity, acquired-diversity, etc.)
- **rules.diversitydimension** - Diversity dimensions (gender, age, race, etc.)
- **rules.source** - Word sources with definitions and Wiktionary links
- **rules.rule** - Main rules with triggers, lemmas, and language
- **rules.alternative** - Alternative word suggestions for each rule
- **rules.trainingsentence** - Example sentences demonstrating rule usage
- **rules.falsepositive** - Text that should NOT trigger a rule

### Linguistic Data Models

- **rules.englishnoun** - English noun forms (singular/plural)
- **rules.englishverb** - English verb conjugations
- **rules.englishadjective** - English adjective forms
- **rules.germannoun** - German noun forms with gender
- **rules.germanverb** - German verb conjugations
- **rules.germanadjective** - German adjective forms
- **rules.frenchnoun** - French noun forms with gender

### Relationship Models

- **rules.rulediversitydimension** - Many-to-many relationship between rules and dimensions
- **rules.rulestructureevaluation** - Rule quality evaluation data
- **rules.lemmatization** - Word lemmatization mappings

## Field Types

### Common Fields

All models with timestamps include:

```json
{
  "created_at": "2023-12-06",
  "updated_at": "2023-12-06 15:39:27.302864",
  "comment": "Optional comment",
  "createdby": null
}
```

**Note:** `createdby` and `ownedby` are always `null` in exports for security.

### Language Codes

- `"en"` - English
- `"de"` - German (Deutsch)
- `"fr"` - French (Français)

### Proficiency Levels (Witty-specific)

These represent the severity/type of language issue, not language learning levels:

- `"unconscious_bias"` - 💡 Subtle biases and assumptions
- `"ancestry"` - Issues related to ancestry/heritage
- `"visible"` - Visible diversity characteristics
- `"language-clarity"` - Language clarity issues
- `"age"` - Age-related biases
- `"invisible"` - Invisible diversity characteristics
- `"inclusive"` - ✅ Positive inclusive language (suggestions to keep)
- `"openly_discriminating"` - 🚫 Slurs and hate speech (severe)

See `data/proficiency_levels.json` for complete definitions and translations.

### Alternative Types

- `"default"` - Default alternative (no special emphasis)
- `"person_first"` - Person-first phrasing
- `"identity_first"` - Identity-first phrasing

### German Gender

- `"m"` - Masculine (der)
- `"f"` - Feminine (die)
- `"n"` - Neuter (das)

### French Gender

- `"m"` - Masculine (le)
- `"f"` - Feminine (la)

## Example Structure

```json
[
  {
    "model": "rules.diversitydimension",
    "pk": 1,
    "fields": {
      "name": "gender",
      "category": 1,
      "proficiency_level": "unconscious_bias",
      "created_at": "2023-12-06",
      "updated_at": "2023-12-06 15:39:27.302864",
      "createdby": null
    }
  },
  {
    "model": "rules.rule",
    "pk": 1,
    "fields": {
      "lemma": "chairman",
      "trigger": "chairman",
      "language": "en",
      "is_prefix": false,
      "emoji": "👔",
      "tags": "gender,leadership",
      "created_at": "2023-12-06",
      "updated_at": "2023-12-06 15:39:27.302864",
      "createdby": null,
      "ownedby": null
    }
  },
  {
    "model": "rules.alternative",
    "pk": 1,
    "fields": {
      "rule": 1,
      "lemma": "chairperson",
      "type": "default",
      "is_advanced": false,
      "created_at": "2023-12-06",
      "updated_at": "2023-12-06 15:39:27.302864",
      "createdby": null
    }
  }
]
```

## Validation

### Using Python Script

```bash
# Install jsonschema if needed
pip install jsonschema

# Validate an export file
python validate_export.py data/rules_database.json
```

The script will:

- ✓ Check JSON syntax
- ✓ Validate against schema
- ✓ Show statistics by model type
- ✓ Report specific validation errors with paths

### Using Online Tools

1. Go to [jsonschemavalidator.net](https://www.jsonschemavalidator.net/)
2. Paste the schema from `rules_export_schema.json`
3. Paste your export data
4. Click "Validate"

### Using VS Code

1. Install the "JSON Schema Validator" extension
2. Open your export file
3. Add this to the top of your JSON file:
   ```json
   {
     "$schema": "./schemas/rules_export_schema.json",
     ...
   }
   ```

## Security Notes

### Fields Nullified in Exports

For security, these fields are ALWAYS `null` in exports:

- `createdby` - User ID who created the object
- `ownedby` - User ID who owns the object (rules only)

These are set to `null` during export to prevent:

- Leaking user account information
- Exposing internal user IDs
- Potential security vulnerabilities

When importing, use `--assign-to=username` to assign ownership to your user.

## Import Options

The schema validates exports, but imports support flexible handling:

```bash
# Basic import with validation
python manage.py import_rules_db --input=data.json --assign-to=user

# Ignore PKs (for merging from different sources)
python manage.py import_rules_db --input=data.json --ignore-pk --skip-existing

# Dry run with validation
python manage.py import_rules_db --input=data.json --dry-run
```

## Schema Versioning

- **Version:** 1.0
- **Schema URI:** `https://witty-works.com/schemas/rules-export-v1.json`
- **JSON Schema Draft:** Draft 7

When the export format changes, the schema version will be incremented.

## Related Documentation

For complete import/export information:

| Document                                           | Purpose                                   |
| -------------------------------------------------- | ----------------------------------------- |
| [Quick Start Guide](../QUICKSTART_SHARING.md)      | Step-by-step scenarios (5-15 min)         |
| [Comprehensive Sharing Guide](../SHARING_GUIDE.md) | Advanced features and workflows (30+ min) |
| [Data Directory](../data/README.md)                | Pre-populated data information            |
| [Main README](../README.md#documentation)          | Full project documentation                |

**Quick Start:** Run `python validate_export.py data/rules_en.json.gz` to validate a compressed export.

## Contributing

When adding new fields to models:

1. Update the corresponding definition in `rules_export_schema.json`
2. Add descriptions and examples
3. Update this README with field documentation
4. Test with `validate_export.py`
5. Update version number if breaking changes

## License

Same license as the main project.
