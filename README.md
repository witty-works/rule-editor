# Rule Editor

## Installation

```
python manage.py collectstatic
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata diversity_dimensions

python manage.py runserver
```

Open http://127.0.0.1:8000/

## Development

To update migrations run:

```
python manage.py makemigrations rules
```