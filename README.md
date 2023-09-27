# Rule Editor 2

## Installation

```
cp .env.example .env
python manage.py collectstatic
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata diversity_dimensions

python manage.py runserver 8100
```

Open http://127.0.0.1:8100/ and login using the credentials used above

## Development

To update migrations run:

```
python manage.py makemigrations rules
python manage.py migrate
```