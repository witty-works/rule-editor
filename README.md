# Rule Editor

A Django-based administrative tool for managing inclusive language rules and metadata used in the [Witty NLP API](https://github.com/witty-works/nlp_api). This application provides a web interface for creating, editing, and organizing diversity and inclusion rules, alternatives, training sentences, and related linguistic data.

## Overview

The Rule Editor serves as the backend content management system for Witty's inclusive language checking engine. It manages:

- **Rules**: Language patterns that trigger inclusive language suggestions (supports English, German, and French)
- **Alternatives**: Inclusive replacement suggestions with multiple options per rule
- **Diversity Dimensions**: Categorization of rules by diversity topics (gender, disability, age, etc.)
- **Training Sentences**: Example sentences for testing and validating rules
- **Linguistic Data**: Declensions, lemmatizations, and word forms for accurate language processing
- **Sources**: References and citations for rule recommendations

The data managed here powers the NLP API that performs real-time inclusive language analysis.

## Features

- Multi-language support (English, German, French)
- Advanced linguistic processing (lemmatization, declensions, word types)
- Hierarchical rule organization with diversity dimensions and categories
- Training sentence validation
- Source attribution and citation management
- Tag-based organization
- Rule evaluation workflow
- Integration with NLP API for validation

## Prerequisites

- Python 3.8+
- Pipenv
- Platform.sh CLI (for database sync)
- SQLite

## Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/witty-works/rule-editor.git
   cd rule-editor
   ```

2. **Set up environment**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to configure:
   - `SECRET_KEY`: Django secret key
   - `NLP_API`: URL to the NLP API instance
   - `NLP_API_USER` and `NLP_API_PASSWORD`: API credentials
   - `DEBUG`: Set to `True` for development

3. **Install dependencies**

   ```bash
   pipenv shell
   pipenv install
   ```

4. **Set up database**

   ```bash
   mkdir database
   python manage.py migrate
   ```

5. **Create superuser**

   ```bash
   python manage.py createsuperuser
   ```

6. **Import starter data** (optional)

   Import pre-populated language-specific rule sets from the `data/` directory (automatically decompressed from gzip):

   ```bash
   # Import English rules
   python manage.py import_rules_db --input=data/rules_en.json.gz --assign-to=YOUR_USERNAME

   # Import German rules
   python manage.py import_rules_db --input=data/rules_de.json.gz --assign-to=YOUR_USERNAME

   # Import French rules
   python manage.py import_rules_db --input=data/rules_fr.json.gz --assign-to=YOUR_USERNAME
   ```

   Replace `YOUR_USERNAME` with your superuser username. You can import one, two, or all three languages as needed.

7. **Collect static files**

   ```bash
   python manage.py collectstatic
   ```

8. **Run development server**

   ```bash
   python manage.py runserver 8100
   ```

9. **Access the application**

   Open http://127.0.0.1:8100/ in your browser and log in with your credentials.

## Development

### Database Migrations

When making model changes:

```bash
python manage.py makemigrations rules
python manage.py migrate
```

### Database Sync with Platform.sh

**Download database from environment:**

```bash
platform mount:download --mount database --target ./database -e [ENV]
```

**Upload local database to environment:**

```bash
platform mount:upload --mount database --source ./database -e [ENV]
```

Replace `[ENV]` with environment name (e.g., `main`, `dev`).

### Database Sharing

The project supports exporting and importing the rule database without user credentials, with advanced filtering capabilities.

### Getting Started with Pre-populated Data

Language‑specific starter exports live in `data/` (kept small so they can be committed safely):

| File               | Language | Rules | Compressed |
| ------------------ | -------- | ----- | ---------- |
| `rules_en.json.gz` | English  | ~2.5k | ~927 KB    |
| `rules_de.json.gz` | German   | ~2.7k | ~840 KB    |
| `rules_fr.json.gz` | French   | ~2.7k | ~1.1 MB    |

Import whatever languages you need (`.gz` files are decompressed automatically):

```bash
python manage.py createsuperuser
python manage.py import_rules_db --input=data/rules_en.json.gz --assign-to=YOUR_USERNAME
python manage.py import_rules_db --input=data/rules_de.json.gz --assign-to=YOUR_USERNAME
python manage.py import_rules_db --input=data/rules_fr.json.gz --assign-to=YOUR_USERNAME
```

Optional bulk import:

```bash
for lang in en de fr; do
   python manage.py import_rules_db --input=data/rules_${lang}.json.gz --assign-to=YOUR_USERNAME
done
```

More details (file sizes, regeneration commands) are in the sharing guide: see `SHARING_GUIDE.md` (sections: _Language-Specific Imports_ & _Data directory_).

### Export Filtering (Overview)

Rich filters are supported (full docs in `SHARING_GUIDE.md`):

```bash
# Language
python3 export_db_standalone.py database/db.sqlite3 data/rules_en.json.gz --language=en

# Dates
python3 export_db_standalone.py database/db.sqlite3 data/created_2024.json.gz --created-after=2024-01-01
python3 export_db_standalone.py database/db.sqlite3 data/updated_recent.json.gz --updated-after=2024-06-01

# Specific rule IDs
python3 export_db_standalone.py database/db.sqlite3 data/some_rules.json.gz --rule-ids=123,456

# Combined
python3 export_db_standalone.py database/db.sqlite3 data/target_en.json.gz --rule-ids=123,456 --language=en --updated-after=2024-01-01
```

Key flags: `--language`, `--created-after`, `--created-before`, `--updated-after`, `--updated-before`, `--rule-ids`, `--dimension` (Django only). See guide for full command reference.

### Import with Update Mode

Import can update existing records instead of creating duplicates:

```bash
# Update existing records
python manage.py import_rules_db --input=updates.json --update --assign-to=YOUR_USERNAME

# Skip existing, only add new
python manage.py import_rules_db --input=new_rules.json --skip-existing --assign-to=YOUR_USERNAME
```

### Export Format

The export format is JSON with a complete schema definition available in `schemas/rules_export_schema.json`. You can validate exports using:

```bash
python validate_export.py data/rules_database.json
```

### Documentation

**Start here based on your needs:**

| Document                                        | Best For                                | Time     |
| ----------------------------------------------- | --------------------------------------- | -------- |
| [Quick Start Guide](QUICKSTART_SHARING.md)      | Getting started, common scenarios       | 5-15 min |
| [Comprehensive Sharing Guide](SHARING_GUIDE.md) | Advanced usage, filters, team workflows | 30+ min  |
| [Data Directory](data/README.md)                | Pre-populated data information          | 5 min    |
| [JSON Schema Documentation](schemas/README.md)  | Export format and validation            | 10 min   |

**Quick Links:**

- **New to imports?** → [QUICKSTART_SHARING.md - Scenario 1](QUICKSTART_SHARING.md#scenario-1-first-time-setup-receiving-shared-data)
- **Want to export rules?** → [QUICKSTART_SHARING.md - Scenario 2](QUICKSTART_SHARING.md#scenario-2-sharing-your-database-without-users)
- **Advanced filtering?** → [SHARING_GUIDE.md - Advanced Usage](SHARING_GUIDE.md#part-3-advanced-usage)
- **Validate exports?** → [validate_export.py](validate_export.py)

### Validation

**Check training sentences:**

```bash
pipenv run python manage.py check_rules
```

This validates that training sentences correctly trigger or don't trigger their associated rules.

## Project Structure

```
rule-editor/
├── rule_editor/          # Django project settings
├── rules/                # Main application
│   ├── models.py        # Core data models
│   ├── admin.py         # Admin interface customization
│   ├── views.py         # Web views
│   └── management/      # Custom management commands
├── data/                 # Initial data and imports
├── database/             # SQLite database files
├── static/               # Static assets
├── templates/            # HTML templates
└── manage.py            # Django management script
```

## Key Models

- **Rule**: Core language pattern to detect non-inclusive terms
- **Alternative**: Suggested inclusive replacements
- **DiversityDimension**: Categorization (e.g., "gender", "disability")
- **Category**: Top-level groupings
- **TrainingSentence**: Example sentences for testing
- **Source**: Reference materials and citations
- **GermanNoun/Verb/Adjective**: Linguistic declension data
- **EnglishNoun/Verb/Adjective**: English word forms

## Contributing

1. Create feature branches from `dev`
2. Make changes and test locally
3. Validate rules using `check_rules` command
4. Submit pull request to `dev` branch
5. After review, changes are merged and deployed

## Technology Stack

- **Framework**: Django 4.2+
- **Database**: SQLite
- **Deployment**: Platform.sh
- **Admin**: Django Admin with Grappelli
- **Dependencies**: See `Pipfile` for complete list

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For questions or issues, please contact the Witty Works development team or open an issue on GitHub.
