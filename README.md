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

5. **Download production data** (optional)

   ```bash
   platform mount:download -e main --mount database --target ./database
   ```

6. **Collect static files**

   ```bash
   python manage.py collectstatic
   ```

7. **Create superuser** (if not using production database)

   ```bash
   python manage.py createsuperuser
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
