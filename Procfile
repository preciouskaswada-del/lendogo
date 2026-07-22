release: python manage.py migrate
web: gunicorn core.wsgi:application --bind 0.0.0.0:$PORT
