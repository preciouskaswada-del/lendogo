FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y libmagic1 gcc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .

RUN python manage.py collectstatic --noinput
RUN python manage.py migrate --noinput

CMD gunicorn lendogo.wsgi:application --bind 0.0.0.0:$PORT
